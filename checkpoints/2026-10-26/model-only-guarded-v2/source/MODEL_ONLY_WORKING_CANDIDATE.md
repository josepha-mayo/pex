# PEX supervisor model-only — guarded v2 reconstruction

**Locally implemented/tested decision machinery. Production model-only transport
is technically disabled. Not live autonomy, V14 parity, or deployment approval.**

Source: `pex-supervisor-model-only-GUARDED-WORKING-20261026-2051`.
The frozen Inspector base (1,072 source hashes) and dated prior v1 (1,078 source
hashes) remain unchanged. This candidate changes 16 source/config/test/doc files;
its selected-source manifest has 1,079 entries. No frontend code changed.

## What works locally

Under test-only admission, actual Strands agents invoke the configured authored
Model and an independent verifier before model-authored feedback can pass existing
owner/workspace/evidence/policy/budget/capability vetoes. Missing/failed/invalid or
uncertain invocations never become deterministic nudges. Scripted verification
probes and automatic sibling handoffs are refused, including delayed history and
dispatch races. Explicit manual handoffs retain separate operator authority.
Durable mode identity prevents old unsent effects crossing modes; uncertain
reservations survive restart without same-event retry or worker resend.

**Every production model adapter is refused**, not merely labeled unqualified.
The gate covers configuration/credential-store/client preparation, loop/router,
SDK stream entry, scheduled inference, AgentCore model-only requests and pending
worker effects. No environment/config/provenance flag enables live operation.
Unrelated configured worker adapters/startup remain unchanged: this is not a
whole-app zero-network promise. Default decision behavior is preserved.

## Evidence

- **67 focused tests passed**, zero network attempts; independent reviewer reran
  all 67 and approved local preservation/testing.
- **556 expanded pytest assertions passed; 3 skipped.** The stricter process-wide
  network audit correctly exits **1** for **10 blocked legacy loopback discovery
  attempts**, not a zero-attempt success. Five default-mode settings tests each
  probe 127.0.0.1:11434 and :1234 during fixture teardown. No socket connect was
  reached. Exact test IDs/ports are in `model-only-verification/NETWORK_AUDIT.json`.
- Skips: Windows-only vault receipt; two optional AgentCore SDK contract tests
  because `bedrock_agentcore.runtime` is not installed. Exact IDs are in RESULT.json.
- Ruff check/format pass for all 14 changed Python files; patch reproduction
  matches all 16 after-hashes. One nonblocking Starlette deprecation warning.
- Real installed Strands1.53.0, authored local Model, real SQLite and synthetic
  worker. **Zero external provider inference; no live benchmark.**

Reproduce focused cases with `./model-only-verification/reproduce-focused.sh`.
The expanded `reproduce.sh` intentionally retains strict network-audit rejection
of the documented legacy fixture attempts; do not call its exit status green.
Runtime uses env -i, disposable HOME, disabled ambient supervisor loading and AWS
metadata discovery. Official PyPI dependency installation was separate. Exact
candidate-interpreter metadata is in DEPENDENCIES.json / RESOLVED_PACKAGES.json;
OpenAI2.54.0 is installed only for mocked legacy interface tests. Python3.12.14
was available, not the repository-pinned3.12.13. This is not full uv sync/full suite.

## Remaining blockers

**Do not expose this historical baseline publicly or use real BYOK credentials.**
Later owner/auth/origin/session hardening has not been restored. Source publication
is only a recovery checkpoint, not a deployment. Managed provider retries,
transport ambiguity, cancellation, raw-wire usage and billing remain unqualified.
Strict usage here validates SDK-observed counters (every cycle, exact int types,
total=input+output and cache reconciliation), not wire values normalized upstream;
OpenAI SDK can coerce boolean/string/floating usage before these checks.
No bounded_repo or remote-evidence feature was enabled. No user PC, Codex task,
external inference or public deployment was used. Public source checkpointing is
handled separately under the user's later explicit instruction.

See `docs/SUPERVISOR_MODEL_ONLY_RECONSTRUCTION.md` and the truthful receipts,
manifests, before/after hashes and patch in `model-only-verification/`.
Exclude dependencies, runtime state, credentials and .env bytes from backups.
