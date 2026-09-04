# Threat model (working)

PEX watches privileged local agents. Treat the bridge as equivalent to having the user's agent permissions.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Prompt injection tries to raise PEX authority | Typed actions + local policy; only human intent grants privilege |
| Secrets in transcripts | Redaction before cloud; local-only sensitivity |
| Cloud exfiltration | Sanitized events; no raw repos uploaded by default |
| Destructive approvals | Always-ask patterns; autonomy levels |
| Wrong-session injection | Session IDs bound as `harness:vendor_id` |
| Loopback port squatting steals the desktop bearer token | Tauri generates a 384-bit operator bearer in Rust memory, gives it only to its owned sidecar environment, and refuses an already-occupied port unless the owner returns a fresh nonce-bound HMAC-SHA256 identity proof. The bearer reaches only the two packaged local webviews after that same proof; a navigation guard rejects remote, query-bearing, userinfo-bearing, data, and JavaScript top-level URLs. WebSocket auth uses a base64url-wrapped subprotocol rather than a loggable query string, and the packaged UI never downgrades to tokenless access. |
| Worker hook compromise becomes bridge-operator compromise | Workers receive only digest-backed hook credentials with exact harness/route/project authority. A pre-registered credential atomically binds to its first vendor session and rejects later cross-session or cross-project use. Hook credentials cannot authorize operator REST or MCP routes and expire, rotate, and revoke independently. |
| Browser cross-origin mutation | Requests carrying an explicit Origin may mutate only from the packaged Tauri origins or the pinned local Vite origin; native hook clients without an Origin still require their scoped bearer. |
| Malformed or ambiguous control JSON | Bounded bodies, one content type, duplicate-key rejection, non-finite-number rejection, strict request schemas, and fail-closed typed action parsing |
| Malicious custom pet assets | Bounded UTF-8 manifests, duplicate-key rejection, in-directory resolved paths, and static 1536x2288 WebP/alpha/transparency validation before import; bundled pets pass the same media validator at build time |
| Workspace links escape the supervised root | Resolved paths must remain below the configured workspace and bounded artifact readers reject out-of-root targets |
| Bridge down freezes Cursor | Hook fail-open |
| Intervention storms | Cooldowns |
| Supervisor hallucination | Locally observed truth overrides conflicts; semantic-only interventions require an evidence-citing independent verifier; typed action validation + policy guard + audit log |

## Trust boundary

PEX does not provide cryptographic isolation from an unrestricted process running
as the same OS user. Such a process may inspect another process's memory or
environment using OS-level privileges available to that user. The concrete
boundary is narrower and testable: PEX does not deliberately place the operator
bearer in worker files, worker configuration, worker arguments, or worker
environment; only scoped hook credentials are worker-visible. The Tauri host
retains the operator bearer in Rust memory, the owned bridge copies it into
bridge memory and scrubs `PEX_TOKEN` before adapters can spawn worker children,
and neither host forwards token-bearing child output or errors.
