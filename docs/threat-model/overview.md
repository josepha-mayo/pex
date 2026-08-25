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
| Bridge down freezes Cursor | Hook fail-open |
| Intervention storms | Cooldowns |
| Supervisor hallucination | Deterministic scores + verifier graph + audit log |
