# Native OpenCode quota-fence check — 10 September 2026

Product source: `5a4c4ac8a3ef6345eb82018a32c85969d9cf0b3f`.
Full Tauri build exited 0; rebuilt release executable opened without Retry.
Both Pex and Von previews loaded. The overlay remained hidden for this test.

## Installer verification

MSI and NSIS integrity verification passed on one bounded retry:
`build/package-5a4c4ac-20260910-retry.json`, SHA-256
`33c5c1bb8c2f19b282541234f1c3e8bfcaecb1cf1ce90633feddb5495c59329f`.
The original attempt retained `package_cleanup_failed` (Windows EPERM), despite
both installer trees verifying. Do not relabel that attempt as a pass.
Installers remain unsigned; this is not a fresh-user installation test.

## Real native negative-case result

- Connected the isolated, loopback-only OpenCode server on the first attempt.
- Selected its existing synthetic goal and resumed only that session. Preserved
  its original three-review allowance, with two reviews remaining.
- Sent one bounded task using pinned `opencode/ling-3.0-flash-fin-free`.
  The task required an exact `status.txt` in the isolated workspace.
- The provider again reported its free usage limit. Native Inspector showed
  **Blocked**, explained the limit, and said PEX was holding automatic follow-ups.
- Aborted only the owned worker session. The resulting `session.idle` event at
  `2026-09-10T21:49:56.179185Z` did not clear the provider fence or trigger a nudge.
- Durable state: 61 fully processed events, `opencode_free_tier_limited: true`,
  status `blocked`. Total model-backed reviews and interventions stayed at the
  pre-test baseline of one each: **zero additional reviews or interventions**.
- Paused the test session through native PEX, verified the persisted pause, then
  stopped only the owned server. Its runner exited 0.

Private, ignored evidence/helpers are in
`build/native-mvp-be67a91-20260910/` (validated receipts and cleanup). No key,
private worker output, or raw provider configuration is published here.

## Limits

This passes the provider-limit/idle suppression case, not successful OpenCode
artifact creation, provider-access recovery, generic cancellation, or a scored
comparative benchmark. Earlier failed behavior remains recorded in the handoff.
Positive Codex/Strands source proofs are documented separately. AgentCore is
offline-tested, not deployed. Overall recording/submission readiness remains open.
