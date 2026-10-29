# WIP: durable owned-sandbox cleanup identity

The reviewed SDK create response now produces an exclusive private ownership receipt before the SDK handle can escape. The receipt binds run, arm, frozen configuration, template, requested timeout, idempotency identity, create/receive timestamps and response digest. It deliberately excludes response tokens, client options, credentials and task content. File and parent directory are fsynced. It is ownership evidence, not allocation, expiry or successful-cleanup evidence.

A failed persistence step retains in-memory ownership and uncertainty; existing evidence/symlinks are never overwritten. Future interrupted-controller cleanup can use the exact recorded ID instead of broad discovery. Historical runs are not retroactively changed.

Qualification: 28 focused tests passed using the actual pinned E2B SDK with exclusively authored local transport responses, including constructor failure, fsync failure, symlink/existing-file refusal, private permissions and secret-field exclusion. No live provider, VM, cleanup or cancellation behavior was established by these tests.
