# Preparation 02 — execution-platform admission failure

Root reviewed the original manifest and granted conditional GO for one narrow
mechanical refresh of the still-unused approved pair. Preparation 01 remains
unchanged, expired and unlaunched. Preparation 02 changed only deterministic run
identity, expiry and required dependent source/config pins. Whitelist checks,
all frozen task/source/predecessor identities and 68 tests plus 14 subtests passed.
The gate checkpoint was pushed and its remote blobs verified before launch.

The once-only launcher was invoked on 2026-10-28 at approximately 14:26 UTC.
It exited with `AdmissionRefused` before the runner created its output directory.
That directory is created before any supervisor ledger, worker or VM construction.
Therefore there were zero new worker requests, supervisor requests or VM creates.
A launcher claim exists and is preserved; no automatic retry was performed.

The launcher recorded exception class, not its error string. A fresh read-only
admission reproduction returned `same_execution_platform_proxy_mismatch`:
the current ordinary platform proxy identity no longer matched the identity frozen
in the previous preparation invocation. The CA path and bytes were unchanged.
This diagnoses a cross-invocation platform-identity problem; no alternate route,
transport bypass or relaxed guard was introduced.

All prior uncertain liabilities remain charged; new Nebius/compute liabilities
are zero. No provider or VM resource was created, so no resource cleanup was
needed. Provider keys were not revoked. Configs, raw evidence and platform state
remain private. No task-quality comparison, benchmark success or PEX lift exists.
The conditional GO required stopping on a failed check, so dependent execution
is paused for parent direction. The same one-run grant has not reached a provider.
