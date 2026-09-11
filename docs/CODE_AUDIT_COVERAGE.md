# PEX code audit coverage — 5 September 2026

## 11 September — AgentCore client boundary full-file audit

Read `services/bridge/src/pex_bridge/agentcore.py` end to end against the core,
build, and implementation-recovery specifications. The client validates exact
session/harness/project/goal binding before dispatch, minimizes and redacts the
cloud request, bounds request and response bodies, rejects duplicate keys and
non-finite JSON, reconstructs every remote proposal under local policy, requires
bound independent-verifier evidence for completion and trajectory corrections,
and treats post-dispatch transport/protocol failures as delivery-uncertain so a
second semantic model is never started. AgentCore mode fails closed to NOOP for
definite pre-dispatch/configuration failures; hybrid fallback remains explicit.
No new defect was found.

The complete local AgentCore client/runtime/pipeline/preflight gate passed
**183/183 in 12.23 seconds** with fake clients and local fixtures. No AWS request,
deployment, paid model call, native app, or worker was started. This proves the
offline boundary contract, not a deployed AgentCore runtime.

## 11 September — shipping OpenCode integration full-file audit

Read `integrations/opencode-plugin/pex-plugin.js` and
`services/bridge/src/pex_bridge/adapters/opencode.py` end to end against the
core/recovery specifications. The plugin accepts only a bare loopback origin and
bounded printable bearer, bounds request/response bytes and JSON depth/nodes,
keeps its session cache bounded, never blocks worker startup on PEX failure, and
applies only active session-scoped instruction/tool overlays. It does not write
OpenCode project configuration or claim permission-hook support.

The production adapter binds every control mutation to the exact discovered
session/workspace, serializes message sends, preserves delivery uncertainty,
polls for an exact new user-turn receipt, bounds retained sessions/inbox/hooks/
permission and lineage state, and treats transport replacement, SSE loss,
invalid observations and removal-tombstone exhaustion as non-authoritative gaps.
Completed assistant messages require exact parent lineage and valid terminal
timestamps; duplicate terminal siblings and their later idle event do not cause
double semantic dispatch. Exact `MessageAbortedError` evidence remains distinct
from completion. Pipeline ingestion retries the same normalized event
idempotently and never replays an old transport into a replacement.

No additional source defect was found in this pass. Verification relevant to
these files includes the clean 4,440-pass full Python regression (32 skipped),
the 290-pass desktop suite (one intentional platform skip), and a fresh
model-free installed OpenCode 1.18.30 production HTTP/session/SSE smoke that
passed 1/1 in 1.32 seconds and progressed Strong → Deep. The server was owned,
stopped, and left zero listeners. This audit does not replace the remaining
packaged, model-backed corrective/quiet journeys.

Full read of `test_opencode_pipeline_pump.py` then confirmed its production-pump
coverage: desktop discovery stays off the event loop and is rate-bounded; session
listing does not invent activity; completed batch prefixes are not replayed;
post-acceptance failures retry the identical event; transport loss marks a gap;
and a retry after durable journal acceptance settles idempotently. The exact
file passes 12/12 with unhandled pytest thread exceptions promoted to failures.

## 10 September — preserve artifact-count evidence through AgentCore

Scoped review of cloud request compaction found artifact metadata retained path
and size but discarded the local reader's `row_count` and `row_count_complete`.
The remote semantic supervisor therefore lost exact count evidence without a
privacy reason: counts can be retained without sending artifact contents.

Added `_artifact_count_metadata`: preserve only nonnegative signed-64-bit integer
counts with literal `row_count_complete: true`. Partial, malformed, boolean,
negative or oversized counts become null/false rather than an exact-looking
clamped value. Older metadata without either count field keeps its prior shape.
Artifact tails remain excluded. This conveys evidence, not a canned decision
or permission to execute a cloud-proposed action.

Nine cloud-envelope cases failed before the fix. After repair, the AgentCore
client/runtime/preflight/pipeline and Strands runtime/integration selection passed
221 tests in 45.39s. Two additional tests then connected the actual local JSONL
reader to cloud serialization: valid 27-row input remains 27/complete; malformed
input stays unknown. Full AgentCore client suite passed 112 tests in 8.84s.
Ruff passed for both Python files. Tests use local temporary artifacts and fake
AWS clients; no deployment, paid request, native app or worker was started.
This source fix is newer than verified package 2f5038e and is not yet packaged.

Follow-through verification extended those two reader cases beyond serialization:
the sanitized request is reconstructed, its real Strands `inspect_workspace` tool
is called, and the returned artifact metadata must match the cloud envelope.
The evidence collector must record the exact returned output and sanitized request
digest. Both cases passed; combined AgentCore client/runtime/pipeline regression
then passed 158 tests in 44.67s. Ruff passed. No additional production change,
model inference, worker or AWS invocation was needed for this offline contract.

## 10 September — Zen Muse protocol and settings constructor repair

Corrected the exact Muse 1.3/1.2 routing against current official Zen endpoint
documentation. Two test cases failed before the fix; 15 selected routing/settings
cases and then all 81 provider tests passed. Added Zen chat and Responses cases
to the settings API's vault-to-model constructor contract. No live model called.
[Commands, intermediate package hashes, warnings and limitations](demo/evidence/ZEN_ROUTING_2026-09-10.md).

## 10 September — connector cleanup safety regression

Scoped read of shared-Codex proxy launch/cleanup, Codex stdio start/close and ACP
start/close found subprocess-object cleanup, not recursive numeric-PID discovery.
This does not establish incident cause or complete those adapters' full-file audit.
Added five fully mocked proxy cleanup cases: graceful exit, terminate escalation,
kill escalation, and process-exit races at both escalation steps. No process is
spawned or terminated by these tests. The assertions check the connector's actual
method calls; they are not OS-level proof that unrelated apps cannot be affected.

Verification command:

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_codex_proxy_process_cleanup.py tests/unit/test_codex_shared_consumer_shutdown.py tests/unit/test_codex_shared_attach.py -k 'cleanup or exit_race or consumer_exits or detach_closes or failed_confirmation' --tb=short
```

The selection also covers consumer cancellation settlement, selected-subscription
detach without turn commands, and failed confirmation preserving the prior adapter.
Result: 8 passed, 22 deselected in 6.78 seconds; Ruff passed for the new test file.
Native safety hold remains in force. No production behavior changed.

## 10 September — public status and submission claim consistency

Audited current entry-point claims in README, STATUS, KNOWN_FAILURES, submission
copy, the historical submission sprint and demo README. Several "current" labels
still selected older packages (9357bb8/933239a), and the sprint retained prior
native-test approval language. Added authoritative 10 September checkpoints and
clearly historical labels without deleting prior evidence. Current package 166a656,
later source-only fixes, selected 423-backend/268-desktop regression scope and
native safety hold now agree across these entry points. No public submission or
posting was performed. All local Markdown links in these six files resolve;
diff whitespace check passes. Read-only Authenticode inspection returned NotSigned
for both current installers, now retained in package evidence.

## 10 September — Codex capture budget and honest fallback evidence

Resolved the capture-history item below without changing notification delivery.
Both memory and stdio transports share `_CodexRawCapture`: at most 8 MiB serialized
payload and 1,024 records, with an immutable-in-practice retained prefix once
saturated. `raw_capture_complete` becomes false when either bound drops a record.
This flag covers retention of accepted notifications, not all raw protocol bytes.
Exact protocol journaling remains a separate path.

The fallback benchmark writer now requires `capture_complete is True`; absent,
false or truthy non-boolean values cannot produce a complete-looking log. Live
notification enqueue/delivery remains independent. No benchmark was run or scored.

Four transport regression cases failed before implementation (unbounded aggregate
payload and no explicit truncation flag). Verification after repair:

- `test_adapter_deep_audit.py -k codex_capture_budget`: 4 passed, 62 deselected.
  Covers byte/count saturation for both transports; stdio fixture is never started.
- `test_pexbench.py -k codex_raw_log_writer`: 6 passed, 147 deselected.
- `test_codex_pipeline_pump.py`: 34 passed in 24.00 seconds.
- Ruff for all four changed Python files and diff whitespace check passed.

This limits serialized capture payload, not total RSS or the live notification
queue's bytes. Native resource use, freeze cause, full transport audit, and live
benchmark completeness remain unproven. No user app or external service was touched.

## 10 September — Codex pump and capture-retention review

Read Codex transport notification append/read-loop paths, pump queue reclamation,
completion waiting, and the benchmark's raw-capture turn reader. The notification
queue has a 1,024-record admission limit and the pump removes successful prefixes.
The separate `raw_capture` retains the first 1,024 notifications even after the
pump drains them. It has no aggregate payload-byte bound. Do not confuse bounded
record count with low measured idle memory, and do not silently truncate capture
further without preserving its incompleteness in benchmark evidence handling.

Current-source verification:

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_codex_pipeline_pump.py --tb=short
```

34 passed in 26.09 seconds. Includes 1,400-notification reclamation, ingestion
retry without lost acknowledgement, exact delivered-turn outcome matching,
same-thread recovery, and passing-test NOOP. These use the in-process App Server
stand-in and temporary SQLite; no real Codex executable is launched. No production
change was made in this checkpoint. Aggregate Codex capture budgeting remains
open, as do native resource measurement and the full transport audit.

## 10 September — integrated retention-to-outcome proof

Added four cases in `test_opencode_outcome_lineage.py` using LiveHttpTransport's
actual retention implementation, OpenCode's actual asynchronous pipeline pump,
normalization, and delivery-lineage matcher. Only stream establishment is replaced
with a no-network stub; no connection is made. The intact control confirms the
exact-parent response. Count eviction, aggregate-byte eviction and an oversized
discard each set non-contiguous lineage and prevent confirmation of the same
otherwise matching response. Each test cancels only its own asyncio pump and
closes its unused HTTP client.

```text
.venv\Scripts\python.exe -m pytest -q tests/unit/test_opencode_outcome_lineage.py tests/unit/test_opencode_pipeline_pump.py --tb=short
```

Result: 57 passed in 4.77 seconds; changed-file Ruff passed. No production change
was needed. This closes the offline cross-layer regression gap, not real worker
delivery, model inference, native acceptance, or the full audit.

## 10 September — dropped SSE frames cannot imply continuous history

Follow-up review of `_read_sse`, `_bounded_sse_lines`, `_decode_sse_data` and
`events_since` found that invalid or oversized observations were silently omitted.
Four mocked HTTP regressions failed: malformed JSON, non-object JSON, excessive
line length, and excessive cumulative frame length. The retained surrounding
observations looked contiguous. `_record_event_gap` now retires the old tail,
advances the absolute cursor, and wakes readers. The line reader emits a discard
sentinel so the complete affected frame is ignored and marked as a gap.

Expanded verification also covers a valid data line following a discarded line
within the same frame (must not salvage it), plus comments/empty keep-alives
(must not create a gap). Results: `test_adapter_deep_audit.py -k 'http or sse'`
16 passed, 46 deselected in 2.42 seconds; `test_opencode_pipeline_pump.py` 4 passed
in 1.38 seconds; Ruff passed. Mock HTTP only: no user server or worker contacted.
This preserves the existing adapter rule that a known stream gap cannot support
authoritative delivery lineage; no live model or native behavior is claimed.

## 10 September — aggregate HTTP event-buffer bound

Read EventBus, HTTP SSE retention/wait/decoder flow, OpenCode pump gap handling,
Codex pump idle discovery and websocket queue/catch-up cleanup. HTTP retention was
bounded only by 1,024 records; each sanitized record could retain 65,536 text
characters plus structural data. Added an 8 MiB aggregate serialized-payload
budget, with explicit per-record size accounting and oldest-record eviction.
An individually oversized record advances the absolute cursor and clears the
previous tail, preserving the contiguous-tail assumption in `events_since`.
The byte figure is a serialized-payload bound, not an exact Python heap/RSS cap.

The new aggregate-budget test failed before implementation (four rows retained
where only one fit). It now passes, including oversize gap accounting. A second
test covers count eviction and Unicode size bookkeeping. Verification:

- HTTP/SSE selection in `test_adapter_deep_audit.py`: 10 passed, 46 deselected.
- `test_opencode_pipeline_pump.py`: 4 passed, using fake transports and mocked
  desktop discovery (one test carries a live_desktop marker but mocks inventory).
- `test_opencode_outcome_lineage.py -k 'retention_gap or removal_tombstone'`:
  2 passed, 47 deselected; gap-marked evidence cannot prove delivery lineage.
- Ruff passed for changed transport and test; diff whitespace check passed.

No user app, real worker or network endpoint was used. This is a resource-bound
repair, not proof that retained SSE data caused the reported machine freeze.

## 10 September — downstream intent and queued-action verification

Reviewed the Store pre-dispatch goal revision/hash comparison, event snapshot
restoration in Pipeline, and recovery completion's existing changed-intent test.
Added two Store regressions for a decision-only change with the Goal model itself
unchanged, and for restoring the original hash at a later revision. Both assert
that the old main effect is denied, remains reserved, and never starts dispatch.
No production change was needed for this guard.

```text
.venv\Scripts\python.exe -m pytest -q tests/e2e/test_recovery_stop_loop.py tests/unit/test_event_processing_pipeline.py tests/unit/test_event_processing_store.py -k 'not abandoned_background_train and not exited_background_job' --tb=short
.venv\Scripts\python.exe -m pytest -q tests/unit/test_generic_dispatch_authority.py --tb=short
```

Results: 86 passed, 2 deselected in 169.73 seconds; 16 passed in 13.16 seconds.
Ruff passed for the changed test. Fixtures disable live LLM/Codex attachment and
mock desktop process inventory. The excluded recovery cases launch background
processes; they were intentionally not run under the native safety hold. These
checks use synthetic worker events and temporary SQLite, not actual Codex/Strands
inference or native UX. They extend regression evidence, not the full-file audit.

## 9 September — partial goal mutation preserves intentional clears

Read the goal PATCH branches, ledger extraction, and Store transaction's revision,
hash, retirement, insert and rollback checks. Initial 70 authority/operation/store/
semantic tests passed. A new in-process API regression then failed in three cases:
rename and override restored a cleared criterion; an unrelated question edit
restored a cleared decision from unchanged objective text. PATCH now extracts only
when objective text actually changes, while explicit ledger replacement remains
unchanged. A fourth case covers resubmission of identical objective text. Each case
also confirms that a subsequent new objective imports its new labeled criteria and
decisions. Final command:

```text
.venv\Scripts\python.exe -m pytest -q tests/e2e/test_goal_lifecycle.py tests/e2e/test_goal_control_operation_routes.py tests/unit/test_public_task.py tests/unit/test_goal_intent_authority.py tests/unit/test_goal_control_operations.py tests/unit/test_goal_store_transaction.py tests/unit/test_goal_intent_semantics.py --tb=short
```

Result: 120 passed in 48.03 seconds; Ruff passed for both changed Python files.
ASGITransport and temporary SQLite only; no UI, native worker or paid model used.
This does not claim a full audit of the large app/store files or full-suite success.

## 9 September — goal ledger edit integrity

Reviewed App goal-evidence loading, draft initialization and save flow against core
section 5 (durable decisions and intentional updates). Edit previously accepted an
empty fallback while decisions were unavailable; malformed successful reads were
also marked fresh. `goalLedger.ts` now validates decision rows and goal identity;
editing requires the loaded goal/revision and fresh decisions. The draft's starting
revision must still match before save. Removed the unscoped post-save read that
could replace another selected goal's view; scoped polling handles refresh.
The new pure-function and source-wiring regression plus the full desktop suite
pass: 268 tests, zero skipped (6.82 seconds). TypeScript/Vite build exits 0.
The first suite run exposed an obsolete assertion for the removed refresh; it was
updated to require scoped refresh instead. No native UI, model or worker was run.
This is a changed-path audit, not completion of the full source or live audit.

## 8 September — idle-freeze report and bounded resource review

Changed-path addendum: read-only contest-profile inspection found a 237,406,792-byte
physical WAL but only 2,195 current indexed frames, identifying retained allocation after
checkpoint cycles rather than an equally large current logical backlog. Store connections
now explicitly set `wal_autocheckpoint=1000` and `journal_size_limit=16777216`.
Bootstrap/audit coverage passes 11/11 and event-processing/pipeline/workspace-recovery
coverage passes 94/94 with Ruff. No user database was mutated; native causality remains
unknown. Commit `bdf257f` is pushed.

Changed-path addendum: the full offline AgentCore/Strands client, pipeline, runtime,
preflight and supervisor integration selection passes 200/200 on current pushed source.
The exact local AgentCore-compatible `/ping` and strict-schema `/invocations` protocol smoke
also passes on clean packaged source `9966a60`, without a model or cloud call. Read-only
deployment preflight remains
NO-GO due to inactive AWS credentials, absent AgentCore/CDK CLIs, stopped Docker engine,
and missing image/runtime ARN. The saved supervisor-choice decoder now also rejects
exponent-overflow floats before schema validation; configuration/settings coverage passes
64 with one Windows-only skip and Ruff. Commit `e591bd3` is pushed. Static pet validation
passes exactly eight built-ins; this is not native visual/playback proof.

Changed-path addendum: parent found production packaging forced a clean PyInstaller
analysis but did not fail on dirty Git state before building the three helpers. Release
mode now requires empty complete porcelain status before PyInstaller; development mode
is unchanged and the later source-fingerprint fence remains. The actual command refused
the protected concurrent edit without rewriting sidecars. Release tests pass 12/12,
desktop passes 259/259, and the production frontend build succeeds. Package/native proof
remains open.

Changed-path addendum: parent found Devin message dedupe advanced before durable Pipeline
ingestion. A transient failure made the poller permanently skip the message; the negative
timed out without a retry. The cache now advances only after callback success and uses one
65,536-entry FIFO of fixed SHA-256 keys instead of 10,000 variable strings per retained
session. Stable event IDs preserve Store-level replay dedupe. The full adapter/session/
fleet gate passes 115/115 and Ruff is clean; no live Devin/native proof follows.

Changed-path addendum: parent reproduced unbounded post-commit presentation fanout. A
blocked event listener plus 200 further durable commits retained 201 tasks even though
production sockets use event publication only to wake their durable ledger tail. One
serial coalescing worker now retains the newest pending hint and guarantees a follow-up
wake for a mid-publication commit. The event/bus/socket/pet gate passes 62/62 and Ruff is
clean. Durable event truth is unchanged; native freeze/resource proof remains open.

Changed-path addendum: parent found isolated Codex `thread/list` had a bounded response
but unbounded cumulative merge. Staged discovery now caps the retained non-desktop union
and preserves prior state on refusal. The process-only desktop tile stays separate.
Codex discovery/pump/attach/protocol/fleet coverage passes 158/158; Ruff is clean. This
is not a live App Server/native proof.

Changed-path addendum: parent extended cumulative discovery-state bounds to OpenCode and
Qwen. Both now stage complete updates, check remote-plus-retained unions and avoid partial
state on refusal. Full adapter/fleet/OpenCode pump/outcome/fork coverage passes 139/139;
Ruff is clean. No live transport or native resource evidence follows.

Changed-path addendum: parent found Devin's page-size guard did not bound cumulative
runtime state across rotating API inventories. Discovery now stages updates, rejects a
union beyond 1,024 retained sessions and cannot partially mutate the prior state on
refusal. The complete adapter-capability/fleet gate passes 84/84; Ruff is clean. This is
offline contract evidence, not live Devin or native proof.

Changed-path addendum: parent found that `Pipeline._session_locks` retained every
historical session ID for the life of the bridge. Weakly retained locks now preserve one
shared lock while any operation owns or waits for it and disappear when inactive. The
original same-session serialization/cross-session parallelism tests plus lifecycle,
retention, shared-status and continuity paths pass 64/64; Ruff is clean. This is a
bounded changed-path resource repair, not native stability proof.

Changed-path addendum: parent traced aggregate repeated-event filesystem work to
prerequisite checks on in-progress `SHELL`/`TOOL_CALL` events. Optional scans now have a
two-second per-session cooldown, a four-per-ten-second global admission window and one
in-flight slot. Throttled evidence is explicit; STOP and requested claim verification
still take fresh snapshots. The combined gate passes 79/79 with one skip and two
deselected subprocess cases; Ruff is clean. Blocked individual OS calls remain open.

Changed-path addendum: parent replaced supervisor `os.walk` inventory with incremental
scanning capped at 4,000 entries, 400 files and two cooperative seconds. Directory changes
and scan-to-stat file swaps now make evidence explicitly incomplete; links/junctions are
not traversed. Relevant coverage passes 131/131 with five platform skips and Ruff clean.
Blocked OS calls remain open.

Changed-path addendum: parent traced the shared ACP pump's 50ms scan across Kimi, Hermes
and OMP. Stdio event/EOF/close and adapter-local prompt/permission queues now wake a
combined first-completer wait; the losing task is cancelled and joined. Two focused gates
pass 74/74 and 83/83 with Ruff clean. No child process/native resource run occurred.

Changed-path addendum: parent traced isolated Codex's 50ms approval/notification scans
into its already-blocking stdout reader. Production transport activity now wakes the
pump, with a one-second deadline retained for discovery and EOF/close wakeups for cleanup.
Codex transport/pump/attach coverage passes 109/109 and Ruff is clean. No worker or native
resource run occurred.

Changed-path addendum: parent traced OpenCode/Qwen 50ms retained-event scans to the live
HTTP SSE reader. Production pumps now wait for event/stream activity, with Qwen retaining
its discovery deadline. Normal SSE EOF now backs off one second instead of reconnecting
without delay. Relevant coverage passes 71/71 and Ruff is clean; memory fakes keep their
bounded polling fallback and native impact remains unmeasured.

Changed-path addendum: parent traced the shared-Codex adapter's 25ms empty-drain loop
through the subscription into the already-blocking WebSocket reader. A transport-owned
arrival/revocation signal now leaves a quiet attachment dormant and wakes it without
claiming worker state. List-compatible fakes preserve direct append/extend tests; five
focused files pass 174/174 and Ruff is clean. Native resource impact remains unmeasured.

Changed-path addendum: parent applied the hatch-pet durability rules to legacy import,
candidate receipt reconciliation and bounded image-provider response parsing. Each
rejected duplicates/constants but admitted exponent overflow. Finite-float parsing now
keeps legacy rows corrupt-visible, blocks receipt finalization/reconciliation and rejects
provider JSON before base64 use. Hatch coverage passes 58/58 and Ruff is clean. No image,
provider call or visual approval was produced.

Changed-path addendum: parent followed durable intervention-audit rows into JSONL
projection and human action/coverage rows into attention metrics. Permissive parsing let
duplicate keys collapse to an exact expected dictionary. Production immutable triggers
blocked normal SQL mutation; isolated tests removed their test triggers to simulate
offline corruption. Strict decoding now prevents projection/counting. Audit/attention
coverage passes 25/25 and Ruff is clean. Remaining Store reads stay under audit.

Changed-path addendum: parent traced lifecycle-resource and permission/lifecycle
resolution getters into cleanup and human-decision callers. These four reads bypassed the
strict Store decoder. Existing binding triggers blocked ordinary mutation; isolated tests
then dropped their test triggers to simulate offline corruption and proved duplicate or
overflow rows fail before reuse. Affected files pass 51/51 with one platform skip and
Ruff clean. Other Store JSON reads and live side effects remain under audit.

Changed-path addendum: parent applied the hatch-pet v2 contract to custom manifest
admission and the exactly-eight built-in fleet checks. Bounded manifests rejected
duplicates/constants but accepted overflow in ignored fields. Finite-float parsing now
precedes version/atlas validation. The complete fleet/import file passes 59/59 and Ruff
is clean. Normal-size motion/direction and native playback remain unreviewed after the
freeze; no asset was regenerated or self-approved.

Changed-path addendum: parent reviewed judge-facing public benchmark and recorded-demo
artifact readers. Both bounded the file and rejected duplicates/constants but accepted
exponent overflow in ignored fields. Whole-document finite-float checks now reject those
artifacts. Benchmark/demo security coverage passes 23/23 with Ruff clean. No benchmark,
live demo or submission evidence was generated.

Changed-path addendum: parent traced JSON/JSONL artifact row counts through both workspace
inspection and claim acceptance. Exponent overflow remained valid after duplicate and
constant checks, so it could contribute to an exact acceptance count. Both independent
readers now require finite floats for every parsed row/document. The negative proves an
overflowed artifact stays incomplete/uncertain. Coverage passes 94/94 with one Windows
skip and Ruff clean. Live supervisor behavior and native stability remain unproved.

Changed-path addendum: parent traced external provider bytes through bounded model-catalog
decode and the review HTTP client's outer plus embedded JSON decoders. All rejected
duplicates/constants but accepted exponent overflow in ignored, usage or answer fields.
Finite-float hooks now precede catalog/usage/answer validation. Provider and review tests
pass 96/96 with Ruff clean. No live provider or Strands authority proof follows.

Changed-path addendum: parent compared the bridge-wide request limiter and AgentCore
runtime's bounded JSON entrypoint against the strict adapter decoder. Both rejected
duplicate keys/constants but accepted exponent overflow before endpoint/model validation.
Finite-float hooks now reject it for typed and headerless bridge JSON and for the runtime
invocation envelope, including ignored fields. The focused gate passes 46/46 with Ruff
clean. This is inbound source coverage, not deployed AgentCore or native proof.

Changed-path addendum: parent traced human-notification delivery through local JSONL
idempotency replay. The supposedly capped file was parsed before its size check, and a
duplicate-key row could impersonate a delivered receipt. The reader now refuses files
already at the 1 MiB cap, caps replay bytes, and accepts only strict JSON receipts. The
negative verifies ambiguous input cannot suppress a fresh alert and canonical replay
still deduplicates. Channel coverage passes 8/8 and Ruff is clean. Cross-process file
mutation/append atomicity and native resource impact remain unproved.

Changed-path addendum: parent traced the bounded AgentCore response bytes through JSON
decoding, envelope binding, Pydantic modeling and local policy reconstruction. Duplicate
keys and `NaN` were refused, but an overflow such as `1e9999` decoded to infinity even
in an ignored envelope field. A negative reproduced the permissive admission. The whole
response now applies a finite-float decoder and fails through the existing uncertain-
delivery protocol path. AgentCore client coverage passes 89/89 and Ruff is clean. This
does not prove a deployed runtime, provider behavior or native stability.

Changed-path addendum: parent compared the adapter strict decoder with the duplicate
local strict decoders used for pet/control files and durable Store rows. Those readers
rejected `NaN` constants but allowed exponent overflow such as `1e9999` to become
infinity. Two negatives reproduced the admissions. Both readers now apply finite-float
parsing before model or authority validation. Control-file, rejection-Store and goal-
operation coverage passes 23/23; Ruff is clean. This is corruption hardening, not a
whole Store/App audit or native stability proof.

Changed-path addendum: parent traced raw editor stdin through the standalone `-S`
Cursor producer and found that permissive pre-bridge canonicalization bypassed the new
strict inbox decoder. Duplicate `conversation_id` selected the last value and `NaN`
survived into a valid compact JSONL row. Two negatives reproduced the bypass. The
dependency-free producer now rejects duplicate keys, non-finite constants and overflowed
floats before compaction; Cursor's stdout response stays fail-open while PEX declines to
write an ambiguous observation. All eight producer helper cases and Ruff pass. This is
source-authority hardening, not producer retention or installed Cursor proof.

Changed-path addendum: parent followed every malformed/permanent Cursor row from its
immutable source offsets through observer acknowledgement, SQLite persistence, authenticated
read projection and the Connections UI. Checkpoint advancement now depends on a durable
content-free rejection receipt; write failure keeps the complete batch replayable. Receipts
are unique by file identity, offsets, raw-record SHA256 and bounded reason, so replay and
restart return the original receipt rather than multiplying alerts. The operator sees a
bounded human-readable count/reason/time summary; payloads, raw hashes and file identities
are not rendered. Backend focused coverage passes 61/61, the frontend view-model gate
passes 70/70, TypeScript and Ruff pass. React review confirmed parallel fetching, bounded
rendering, stable keys, accessible status copy and stale-failure clearing. Earlier-history
atomicity and producer-coordinated disk retention remain open.

Changed-path addendum: parent traced raw Cursor JSONL decoding through immutable batch
admission and permanent semantic rejection. The event reader still used Python's
permissive `json.loads`, so duplicate keys silently became last-key-wins values and
non-finite `NaN` entered an RFC-JSON protocol boundary. A negative reproduced both
admissions. Event rows now use the existing strict decoder already required by the
checkpoint format; ambiguous/non-standard rows are skipped within the bounded physical
batch and a later valid row remains deliverable. Focused inbox/observer coverage passes
42/42 and Ruff is clean. This does not add the still-open durable rejection receipt/UI
or producer-coordinated retention.

Changed-path addendum: parent traced parsed Cursor inbox records through adapter session
shape checks, normalization, durable Store upsert, event ingestion and acknowledgement.
Previously any valid JSON dictionary that deterministically failed adapter validation
replayed the complete batch forever. Normalization now precedes durable upsert, both
adapter validation phases map to HTTP 422, and only that observer-specific permanent
classification is skipped. Collision, timeout, authority, Store and cancellation tests
prove replay is retained. Combined unit/contract Store-hook coverage passes 41/41 with
Ruff clean. This is changed-path poison isolation, not durable rejection audit/UI or a
producer retention protocol.

Changed-path addendum: parent re-read the complete Cursor inbox reader, versioned
checkpoint decoder, digest-bound acknowledgement and async consumer. A newline-free
record above `MAX_RECORD_BYTES` previously returned no batch and replayed its same
prefix forever. Checkpoint v2 now carries a strict boolean discard state under the
existing file identity/anchor; chunks advance within the total byte budget, suffixes
cannot parse as records, and normal admission resumes after newline. Existing v1/legacy
markers remain readable. The negative failed first; all 33 inbox/budget/idle-observer
checks and Ruff pass. This is full changed-path review, not an interprocess producer
protocol, semantic poison receipt/UI or total file-size bound.

Changed-path addendum: parent traced `current_projection()` from its session authority
snapshot through shared Goal caching and per-session artifact readers. A later sibling's
authority exception popped the Goal but did not retract an earlier accepted sibling or
its collected artifacts. The new hostile fake reproduces this mid-read quarantine race.
The projection now rejects the complete Goal scope in that snapshot, including earlier
and later siblings plus collected interventions/events. Related unit/E2E authority
coverage passes 28/28 and Ruff is clean. This is changed-path fail-closed review, not an
atomic multi-artifact snapshot or whole Pipeline/Store approval.

New-path addendum: `tests/unit/test_overlay_expiry_idle.py`. Parent reviewed the
lifespan task owner, `ActionExecutor.expire_overlays()` pagination/serialization and
shutdown stop path. The owner previously swept an empty Store every second and retried/
logged failures at the same fixed rate. It now backs empty waits to eight seconds,
resets on real expiry work, backs failures to 30 seconds and keeps stop-event waits.
The negative failed before implementation; loop/lifecycle coverage passes 10/10 with
Ruff clean. Parent also re-read supervisor configuration daemon-call, staged-secret,
commit-revocation and shutdown ownership; its hostile selection passes 11/11. This is
changed-path and focused transaction review, not whole `app.py`/Executor/Store approval,
native resource proof or freeze-cause identification.

Changed-path follow-up: parent traced discovered-session merge authority from all five
desktop adapters through Store binding checks and upsert. Existing rows now resolve in
strict per-adapter chunks of at most 1,000 instead of singular connection/transactions;
missing rows, goal/pause/status merge and ordered writes are unchanged. The negative
failed before repair; combined related coverage passes 53/53, focused refresh 3/3 and
Ruff is clean. Sequential writes, total adapter volume, whole Pipeline/Store and native
stability/freeze causality remain outside this approval.

Changed-path follow-up: parent reviewed the complete desktop refresh lock/backoff,
shared process snapshot, discovery merge, vanished-row classification and CAS detach
path. Retained controls previously used one query per listed session; the existing
bounded exact-ID batch now supplies one canonical receipt map before the unchanged
checks. A singular-reader-fatal negative failed before repair; combined related tests
pass 52/52 with Ruff clean. Newly discovered authority reads/upserts remain singular;
this is not whole discovery, Pipeline, Store, native stability or freeze-cause approval.

New-path addendum: `tests/unit/test_pet_snapshot_coalescing.py`. Parent traced all
Pipeline/AppState/websocket/direct pet snapshot callers, event presentation scheduling,
shutdown ownership and mutable decoration. Concurrent callers now share one shielded
build and receive deep copies; committed-event bursts use one 250ms serial worker with
a dirty follow-up instead of task-per-event fanout. Hostile copy/cancellation/shutdown/
36-event tests pass 4/4; adjacent event/socket 11/11 and event-processing/projection
60/60 pass; Ruff clean. A broader handoff-filter mix was interrupted after 28 dots and
is not green evidence. This is changed-path concurrency review, not whole Pipeline,
native resource, stability or freeze-cause approval.

Changed-path follow-up: parent re-read pet/current-projection sequencing and the
promptable collapse contract. Artifact enrichment previously preceded the pet's
deduplication of same-goal historical sessions. A real-Store negative observed two
intervention/event authority calls for one returned worker; the closed pet-only mode
now collapses the already-authoritative list first using one shared timestamp. The
general deck/default path stays complete. Related gates pass 55/55 and 26/26 with Ruff
clean. Distinct live groups and deck artifact fanout remain; no whole Pipeline/Store,
native stability or freeze-cause approval follows.

New-path addendum: `tests/unit/test_current_projection_session_batch.py`. Parent read
the complete session/goal/project authority loaders, singular transaction API,
`current_projection`, both consumers and the new tests. The projection previously
opened one configured connection/read transaction per forensic session; it now uses
one bounded coherent transaction for at most 1,000 validated unique IDs and rebuilds
the original recency order. Strict blocked identity behavior remains the batch default;
only the present-tense projection opts into omitting such historical rows. Negatives
failed before repair; final related gates pass 41/41 and 25/25 with Ruff clean. This is
changed-path review, not full-file approval of large Store/Pipeline modules, complete
artifact-query optimization, native stability evidence or freeze-cause approval.

New-path addendum: `tests/unit/test_pet_control_batch.py`. Parent reviewed AppState's
complete `live_pet` path, Pipeline pet projection/promptable collapse, the Store
single-read receipt, existing JSON-list query pattern and new bounded batch. Two
negatives first failed on the missing batch API and legacy per-session call. The
repaired route uses one statement for at most 1,000 unique exact IDs and preserves
revision/control_revision; both batch and singular cursors close. Final related
pet/control/discovery/lifecycle gate 45/45 plus Ruff clean. This is not whole Store,
projection, native-resource or freeze-cause approval.

Changed-path addendum: parent reviewed bootstrap-status ownership across App,
`startupRecovery.ts`, the native status command/identity monitor and visibility store.
Main/settings pages now stop bootstrap IPC when hidden, poll startup/failure at 750ms,
and back ready observation off to five seconds; re-show immediately reads current
native state. Focused startup/visibility 22/22, all desktop 248/248 and TypeScript
no-emit pass. One focused SSR run warned that Vite HMR port 24678 was occupied but
passed; no unknown process was touched. This is not native monitor, CPU or freeze proof.

New-path addendum: `tests/unit/test_idle_event_pumps.py`. Parent reviewed the adapter
registry, all eight pump-capable default adapters, settings attachment ordering and
each runtime attach call site before changing the common starter. Event pumps with a
declared transport/ACP slot now remain dormant while every slot is empty; adapters
without such a slot retain their prior always-on contract. Configured startup,
post-verification HTTP/ACP attach and direct isolated-Codex attach still start normally; existing starters remain
idempotent. The negative first showed four fake pumps starting; final related gate is
60/60 with Ruff and scoped whitespace clean. This is not whole app.py/adapter approval,
native resource proof or freeze diagnosis.

Changed-path addendum: parent reviewed every changed `App.tsx` visibility guard,
effect cleanup/dependency list, event-socket reconnection path and canonical-resource
freshness reset, plus the full new/adjusted source-contract tests. Hidden webviews
now release UI pollers/readers and their socket; visible views immediately resume
canonical reads and durable-cursor catch-up. Cached state loses mutation authority
while hidden. Focused visibility/settings tests pass 41/41, all desktop tests pass
247/247, and TypeScript no-emit exits 0. This grants no whole-App audit, rendered or
packaged proof, native resource measurement, bridge-loop approval or freeze diagnosis.

Changed-path addendum: parent reviewed the full Codex pump's transport transition,
discovery and event-loop ordering plus the central shared-snapshot discovery owner.
Transportless pumping no longer calls the `tasklist`-capable desktop fallback every
second; attached App Server discovery and the central tile remain. The deterministic
negative failed one call on prior source and passes zero after repair. Complete Codex
pump tests 33/33, existing-session/pet discovery tests 42/42, Ruff clean. This is not
a whole adapter audit, live CPU receipt, native stability result or freeze diagnosis.

Changed-path addendum: parent reviewed the supervisor proposal-to-pipeline action
boundary, verification-action binding order, ActionExecutor worker dispatch split,
and the new focused tests. Empty/non-string worker text and explicit Recovery Spec
boilerplate now fail closed before durable intervention dispatch; executor defense
also covers direct/claimed paths. Specific anchored corrections and structured
handoffs remain valid. Focused overlapping evidence is pipeline 10, executor 7,
supervisor/claimed correction 32, plus Ruff clean. A broader event test-file run
stalled after 13 tests and was terminated; it grants no coverage. Protected loop.py
was read but not edited: its empty-action allowance is now contained downstream,
while its unreachable duplicate raise/blank diff remains a final-cleanup item.

New-path addendum: tests/unit/test_cursor_observe_idle.py. Parent reviewed the full
new delay/loop tests and Cursor observer idle-delay wiring in app.py. The fallback
now backs off only on no valid records, resets after work, retains failure backoff
and interruptible stop. 30 observer/inbox tests and Ruff pass. No independent review,
live Cursor timing, whole app.py/observer approval or native resource proof implied.

Parent reviewed AppState event-socket registration/broadcast cleanup and the full
wake-driven websocket tail change. The new TestClient test covers caught-up sleep,
post-commit wake, durable page delivery and no resumed fixed polling; broadcast and
detach coverage prove a raw hint is not delivery. 16 targeted socket/publication/
broadcast tests and Ruff pass. No independent review on this follow-up, full app.py
approval, native resource proof or freeze-cause claim. Five-second fallback remains.

Parent reviewed the event socket tail/queue and the event_publication_page bounds
query plus relevant table/trigger/index definitions. Only the bounds query/cursor
lifetime was changed; two VM-work negatives reproduced a linear idle-history scan.
The complete three new publication tests and changed query were reviewed by parent;
Terra independently found no regression. Targeted publication/socket/broadcast:
15 pass, Ruff pass. This grants no whole-store/app audit or native resource proof.

New-path addendum: apps/desktop/src/pageVisibility.ts. Parent reviewed the complete
visibility store, CodexSprite motion guard/CSS hints, PetStage pointer cleanup and
App visibility forwarding. One SSR negative failed before repair; helper/source
coverage verifies listener sharing/cleanup and mounted-state preservation wiring.
Final focused desktop: 223 pass/zero skip, TS exit 0. React review checklist used;
no independent reviewer added on this slice. Native visibility/timers, GPU/CPU and
full App/source audit remain unverified; eight atlas assets and timings unchanged.

Parent reviewed the full boundedSingleFlightRead helper, six new functional cases,
the App bootstrap callback and source-wiring test. Terra's bounded read-only review
found no concrete regression and suggested shared-caller cancellation coverage;
parent added and verified it. Final nine-file serial desktop selection: 220 pass,
zero skip; TypeScript no-emit exit 0. No whole-file App/native audit approval is
implied. The native call itself remains uncancellable, and the cap is per webview.

Parent-only follow-up review covers the complete versioned checkpoint parser,
device/inode/boundary validation, legacy replay migration and incremental line
reader, plus nine new tests and changed format expectations. Three restart negatives
failed before repair; final targeted inbox/contract selection is 36 pass/44 deselect
and Ruff passes. Small-boundary validation does not prove whole historic-file
integrity, atomic filesystem behavior, installed-app behavior or native stability.

New-path addendum: tests/unit/test_cursor_inbox_delivery.py. Parent reviewed the
entire new two-phase cursor_inbox reader and its two test files, changed app observer/
shared preparation blocks, and changed Cursor contracts. Terra reviewed HTTP-vs-
durable admission, then the implementation; its missing observer-deadline finding
was integrated as a cooperative failure boundary and parent-rechecked. 27 targeted
inbox checks plus 6 HTTP behavior checks and Ruff pass. Source review leaves explicit
generation, atomic path, poison-record/receipt, long-record, retention and resistant-
cancellation findings open. Full app.py/Pipeline or native approval is not granted.

New-path addendum: tests/unit/test_cursor_inbox_budget.py (nine tiny cases). Parent
read cursor_inbox.py fully plus its producer and runtime-loop call site; Terra
reviewed the final reader/test slice, finding no new regression. Six read/offset/
batch negatives and a destructive-backlog negative failed before their repairs.
13 targeted positives / 44 deselected and Ruff pass. This is not whole Cursor
reliability approval: pre-ingestion marker advancement, path safety, synchronous
I/O, oversized incomplete records and producer-coordinated retention remain open.

Changed-path review: App.tsx view cancellation and two-stage history publication,
the complete boundedReadBatch helper and its functional/source tests in readBudget,
and revised signal expectations in supervisorDraft/viewModel tests. Terra's bounded
review found no batch/cancellation issue; its follow-up found an early stale return
that could let a serial poll overlap unfinished status expansion. Parent repaired
that exit and rechecked the diff. Final 213 focused desktop tests and TS no-emit
pass. No whole-file App audit or rendered/native proof is implied. The checkpoint
preserves the initial source-wiring failure and stale-regex development failure.

New-path addendum: `tests/unit/test_observe_budget.py`. Parent and Terra reviewed
observe.py's workspace reader and its reachable Pipeline call sites; the entire
new budget test and changed security test were reviewed. External hardlink/open
replacement and redundant hashing negatives reproduced on prior code. Independent
follow-up review found an enumeration-budget gap and queued-directory replacement;
parent integrated bounded scandir and identity checks, correcting a Windows
DirEntry.stat identity regression exposed by the normal nested-tree control.
Final scoped verification is 18/1skip/2deselected plus 7 pipeline and 1 streaming
hash test, with Ruff passed. Final reviewer found no new regression but retained
non-atomic enumeration, blocked OS calls and aggregate repeated-event limitations.
See the checkpoint and KNOWN_FAILURES; no full repository/native proof is implied.

New-path addendum: `tests/unit/test_discovery_budget.py` (nine in-memory cases).
Parent read discovery.py and reviewed the complete-response timeout, explicit
loopback proxy/redirect policy and pre-append byte bound. The new test file was
reviewed in full. Four negatives on prior code and 18 targeted positives are
recorded in the checkpoint. No live process enumeration, sockets or model calls
were made by these fixtures. This does not grant native stability or full adapter
coverage; process enumeration/executable resolution are outside the new HTTP budget.

Follow-up changed-path review covers goal polling in App.tsx, cancellation in
readBudget.ts, loading-only supervisor status and its revision/sequence helper in
supervisorDraft.ts, and both focused test files. Two goal negatives and one loading
wiring negative failed before implementation. Final scoped desktop selection:
207 passed, TypeScript no-emit passed. Terra independently found no actionable issue
in these effects or the final keyed pet cache. No whole-file/native stability claim
is added by these reviews; the exact verification command is in the checkpoint.

Parent reviewed App.tsx polling/read/asset lifecycle, new readBudget.ts, canonical
activation-state projection/copy, and pet validation concurrency. Independent Terra
review caught the first global-lock approach delaying completed cache hits; it is
replaced by keyed shared work, a two-decode cap and bounded follower wait. Negative
reproductions and 112 desktop / 15 backend scoped positives are recorded in the
current checkpoint. Root cause of the reported whole-PC freeze remains UNKNOWN;
full clean regression was interrupted. Native/resource proof and whole-file audit
coverage are not granted by these diffs. No native relaunch or large gates without
renewed bounded-run confirmation.

## 8 September — named-artifact and descriptor-bound read slice

See [the current checkpoint](CHECKPOINT_2026_09_08.md) for Q18 causal evidence,
negative regressions and exact receipts. Parent reviewed changed evidence_tools.py,
workspace.py and four affected test files; bounded independent Terra review caught
falsey path validation and a private-hardlink swap race, both repaired. Three race
negatives failed before the checked-descriptor fix. Scoped regression:189 passed,
5 host symlink skips. This does not mark the whole source inventory reviewed.
The operator-owned loop.py tail is excluded and unchanged. The one historical
configuration-save 503 is unreproduced after 49 focused and 30 diagnostic repetitions;
its cause remains unknown and the improved assertion preserves any future response.

## 7 September — cancellation cleanup could erase real inference provenance

Live Q14 showed a correct worker completion followed by Muse HTTP 200 and a tool-turn
HTTP 429. `run_strands_async` reached its inner wall but synchronously awaited the
cancelled provider task without a cleanup bound. Pipeline's later 70-second boundary
therefore finalized `planner_failed_after_dispatch_marker`, and the public intervention
projection lost `model_name`, `local_invocation_id`, call count and `used_llm=true` even
though inference had started. This violates Core/Build inference provenance and Recovery
auditability requirements. The repair introduces bounded cancellation draining for both
main and independent-verifier invocations, consumes a late task result without logging
provider content, and annotates whether cleanup finished or remains pending. A deliberately
cancellation-resistant task proves the caller returns before provider cleanup. Focused
runtime: 48 passed. Broader Strands/supervisor/Pipeline/AgentCore: 100 passed in 90.64s,
JUnit SHA256 `F3DF38CF241369A0ADFBC9178CE40670CCA90DF42B42001D45A9FD690F9DE097`.
Live semantic re-verification is pending; severity P1 because action stayed fail-closed
NOOP but the audit trail was incomplete.

Snapshot: 341 unique tracked or untracked source/configuration paths from the current checkout. Includes tests and fixtures. Excludes generated dependency lockfiles and node_modules/target/dist/results/_audit trees; release dependencies, raw evidence, assets and prose docs need separate targeted checks. This is an inventory, **not evidence that every file has been reviewed**.

All entries start `PENDING` for the fresh independent audit. Replace status only with specific coverage evidence from the reviewer; reading a diff, searching a symbol or passing a test does not equal full-file review. Record unresolved findings in SHIP_CHECKLIST.md or a linked findings log. New source files must be added and changed files re-reviewed.

9 September Windows ownership addendum: full read of
`packages/protocol/src/pex_protocol/windows_job.py`; added opened-thread owner
verification before resume. Full new-file review of
`tests/unit/test_windows_job_ownership.py`: all Windows/process calls mocked,
unknown/mismatched/matching owner cases, ordering and cleanup assertions.
3 passed; scoped Ruff passed. Not a real-process test or incident root-cause proof.

## New-path addendum and bounded repair review

### 7 September 22:30 UTC — bounded liveness, pet provenance and canvas review

`7a1a5b5` repairs four directly reproduced async event-loop starvation paths in
bridge app/discovery; old-code negatives and clean114/2skip regression retained.
Independent review of pet lineage led to immutable full-pixel verification, actual
archived review bytes and recomputed majority/cardinal gates, without invented fresh
visual approval. The parent reviewed those diffs and eight node tamper tests.
Native restart/hide/restore passed, then exposed a separate pet.html `html` versus
styles.css `:root` specificity conflict. A pet-only stronger selector is regression
tested (failed before, passes after); desktop215 and TS/Vite pass. Native rebuilt
transparency is pending. These are bounded changed-path audits, not full-file closure
for all 341 inventoried paths and not full submission approval.

### Current whole-pipeline diagnostic — 7 Sep

Q11 is not source-audit closure or a formal benchmark row. It proved the repaired
local timeout chain through real Codex+Strands: Muse main inference, bounded evidence
tools, second verifier, specific same-worker verification request, delivery receipt
and observed unsatisfied outcome. The deliberately isolated fixture accidentally made
the exact pytest command fail on temp setup; PEX correctly intervened rather than
accepting the worker's post-edit completion. Parent tests with a safe temp path passed
8/8; immutable inputs match. This validates the affected runtime route but does not
complete quiet false-positive measurement, native UI, AgentCore deployment or the
path-by-path repository audit.

### Bridge-to-supervisor timeout alignment — 7 Sep

Changed-path review of Pipeline's local/remote semantic invocation boundary and
post-dispatch uncertainty receipt. Q10's provider returned HTTP200, then the bridge's
independent30-second `wait_for` cancelled the60-second main-agent repair. Local calls
now have a70-second outer budget; remote AgentCore remains30seconds. Unexpected
post-dispatch failures retain only the exception class, never message text.83 affected
tests and Ruff passed. Q10 remains failed evidence; source tests do not replace a fresh
whole-pipeline live proof. The protected `loop.py` tail remains outside this review.

### Main Strands wall budget — 7 Sep

Changed-path review of `loop.py` timeout selection and its bounded-timeout unit
contract. Fresh Q09 proved the Zen session repair worked but the full main Agent
timed out at25071ms despite provider I/O allowing45seconds. The main invocation now
has a60-second default and hard maximum; the independent verifier still uses the
existing25-second default ceiling. Timeout cancellation and fail-closed NOOP behavior
are unchanged.126 provider/import/Strands tests and Ruff passed, followed by one
real free-Muse Strands contract in17.47s. Q09 remains a failed quiet case; a synthetic
provider contract does not relabel it. The protected operator tail in `loop.py` is
outside this review and must remain unstaged.

### Zen free Responses session enforcement — 7 Sep

Changed-path review of provider construction plus live failure evidence. Q08's real
Strands request failed400 `MissingSessionID`; fallback NOOP remained fail-closed and
is explicitly not a quiet-pass. A minimal non-sensitive probe reproduced the failure,
then passed with only `x-opencode-session`. Production creates a new opaque
`pex_[32 hex]` value per Zen Responses model instance. It sends no worker/user/
project identity and no OpenCode client impersonation; chat routes and non-Zen
providers are unchanged. Two construction assertions cover format, uniqueness and
forbidden headers. Gates:79 provider/import tests,153 broader supervisor tests,
Ruff, and one real Strands/Muse contract call. The previously green `b1d1223`
installer is superseded and requires a clean rebuild after this source repair.

### Rendered desktop surface audit — 7 Sep

Changed-path review of `Inspector.tsx` plus browser-rendered review of Home,
Inspector, Deck and Settings at 920x700. No-intervention state no longer claims an
action was recorded. The status bubble is independently dismissible and the
dismissed Home state was visually confirmed. All four routes produced no browser
errors; 205 desktop tests and the TypeScript/Vite production build passed. Because
the isolated browser fixture had no native bridge, the 0/8 pet roster and fallback
pet marker are explicitly not pet-asset failures or native runtime evidence.

### Provider Responses import boundary — 7 Sep

Changed-path review of the OpenAI-compatible construction branch and isolated
startup tests. Chat-only routes formerly imported and cached the custom Responses
subclass unnecessarily; this made class identity depend on temporary integration
substitutions and caused the clean full suite to fail after3103passes. The import
now occurs only for catalog entries explicitly routed to Responses. Four exact
route tests,99 provider/lazy/evidence/loop cases, then78 provider plus subprocess
import-boundary cases passed. No live inference, endpoint, credential, timeout or
provider fallback was changed. Full final-source regression remains open.

### Native startup follow-up — 7 Sep

Changed-path review: deferred Strands tool/Responses imports, initial Store schema
transaction and startup source wording. Added `test_bridge_lazy_supervisor_imports.py`
and `test_store_bootstrap.py`: cold no-model import gate, failed-DDL rollback,
existing-data preservation, retry and unchanged FULL/WAL durability.99provider/
evidence/loop tests,68Store-related tests,200frontend tests and build passed.
Actual old candidate cold start and Retry timed out. Rebuilt native proof and full
regression remain open. This is bounded repair review, not full-file audit closure.

### Review allowance visibility — 7 Sep

Changed-path review: Store indexed count query (1000-ID bound, no mutation),
pipeline effective-cap projection, authenticated deck route, App observation
merge, Inspector/types/view-model and regression tests. No new polling/model
call; delayed pet data cannot overwrite newer deck allowance. Counts remain
reservations, not token/dollar usage; invalid/stale/offline values are unknown.
74 pipeline/Store/pet tests and 49 settings/API tests passed. Frontend 199 passed
including rendered Inspector and merge ordering; build passed (63 modules).
React checklist applied to derived rendering and canonical guards. No native
approval or full-file audit is claimed. Handoff contains receipt hashes.

### Saved supervisor limit — 7 Sep

Changed-path review of Settings/App/draft helpers, supervisor API/config, pipeline
effective-cap lookup, Store disabled-candidate refusal and their tests. The saved
override does not mutate startup settings, credential audiences or reservation
counts. Revision/CAS and failed-write behavior are retained; old bridge responses
disable the new editor rather than submitting an implicit reset. React checklist
review added no effect/polling loop and retained disabled-in-flight inputs and
draft/request guards. Gates: 196 frontend tests/build; 106 backend tests plus one
platform skip; final ten dispatch/interleaving cases passed. Not native UI proof.

### Material trajectory review — 6 Sep

9 September follow-up: re-read trajectory detector fully. Repaired equal-timestamp
material-event ordering ambiguity using an uncertainty boundary rather than
input-order inference. Regression failed before repair; trajectory/loop/pipeline
63 passed, scoped Ruff passed. No live review or native checks performed.

Full new-file review: `services/supervisor/src/pex_supervisor/trajectory.py` and
`tests/unit/test_trajectory_review.py`. Changed-path review only: protocol request,
loop routing/prompt/verifier, evidence tools, Codex normalization, AgentCore
redaction/result verifier, planner dispatch and Store reservation transaction.
The review caught cloud filtering that would discard eligibility/evidence and
STOP-only remote verifier enforcement; both were repaired. 293 affected tests
passed, then 96 trajectory/client tests passed for the remote verifier follow-up.
No claim of whole-file Store/pipeline audit, native proof or live trajectory success.

### Context and dispatch project boundaries — 6 Sep follow-up

New `tests/unit/test_bridge_project_binding.py`: full-file review; nine cases.
Changed-path review of mesh, supervisor-context, pipeline and executor project
comparison gates. Each formerly normalized opaque/POSIX identifiers as Windows
paths. Shared conservative comparator now gates context eligibility before
supersession, sibling matching and lifecycle/handoff project checks. Regression
evidence: eight mesh red cases; four supervisor-envelope red cases; eight
pipeline/start-action red cases. Passing gates: 115 context/handoff cases,
34 supervisor/autonomous-context/mesh cases, then 112 dispatch/lifecycle/workspace
cases (overlapping counts, not additive). Thread warnings treated as errors.
This does not close live cross-harness proof or full-file pipeline/executor audit.
Store's legacy comparator remains pending: it also affects persisted request
fingerprints and legacy/v2 aliases, so a global replacement is not yet justified.

Store follow-up: live `_same_project` now uses conservative comparison, while
legacy fingerprint/display spelling and lookalike quarantine remain byte-for-byte
behaviorally preserved. Four red database-backed cases before repair; six full
identity/fingerprint/MCP/operator files passed (45 tests). Explicit active v2
matching branch and database schema unchanged. This closes the bounded fallback
comparison defect, not the entire Store audit, display-query normalization or
all replay/migration scenarios. Full integration regression remains open.

### Project comparison boundaries — 6 Sep

New file `packages/protocol/src/pex_protocol/project_binding.py`: full helper
review. Changed-path review of supervisor protocol, AgentCore client/runtime and
their tests. Replaces three duplicated, unconditional case-folding comparators;
opaque/POSIX identifiers stay exact, Windows drive spelling reuses the existing
conservative path normalizer. Eight red cases preceded repair; final five-file
gate 175 passed with thread warnings as errors. Does not authorize aliases by
filesystem resolution, change physical identity proofs or establish all-project
compatibility. `project_identity.py` has no final diff.

### Fenced example versus persistent intent — 6 Sep

Root fully read `public_task.py` and `test_public_task.py`; changed-path review
of the HTTP goal lifecycle regression. Build spec 14.2 requires persistent intent
extraction, not promotion of examples into actual decisions/requirements. Five
red unit cases exposed that promotion for backtick/tilde fenced examples. The
repair leaves objective text intact while excluding fenced content from lifted
lists. Matching/longer closing fences and unclosed examples are handled;
explicit supplied fields retain their existing precedence. Both complete test
files passed: 30 tests, thread warnings as errors. This does not cover every
Markdown construct, all intent ambiguity or semantic extraction quality.

### Trajectory candidate integrity — 6 Sep, through `f650260`

Root fully read `services/supervisor/src/pex_supervisor/drift.py` and
`tests/unit/test_drift.py`; changed-path review covers planner, planner tests
and the two synthetic HTTP trajectory cases. Observed defects: basename-only
overlap conflated different files; matching files/commands and broad-edit lexical
signals were promoted to unverified corrective messages. Repairs preserve exact
normalized paths and event provenance, reject invalid sibling/action/time scope,
and retain candidates without deterministic drift accusations. Focused gates:
50 unit tests, plus 13 selected unit/API checks. These are not semantic decision
or live worker evidence.

Remaining P0: ordinary mid-task events do not normally enter semantic inference
(`loop.py` currently gates it to STOP unless forced). Root read that gate but
has not modified the protected dirty file; user permission was requested.
Do not mark trajectory supervision complete merely because incorrect automatic
messages have been removed. It requires goal-aware evidence gathering, budgeted
semantic review, justified intervention, observed continuation and outcome proof.

### Low-quota evidence and pet interaction repairs — 6 Sep

Root changed-path review, not a full-file or whole-codebase signoff:

- `verify.py`, `test_verify.py`: pathless edits invalidated observation summaries
  but not stale-result verdict/probe gates. Four red regressions before
  `366eb07`; focused verifier/evidence-tools gate 70 passed. `bc39de5` rejects
  boolean/negative artifact counts; eight count cases, three red before repair.
- `workspace.py`, `test_workspace_inspect.py`: `46fc12a` enforces actual bounded
  artifact reads instead of trusting an earlier stat. Two stale-size cases red
  before repair; exact-limit JSON/JSONL compatibility retained. Combined
  workspace/verifier/evidence-tools gate 97 passed, one skipped. No atomic
  snapshot guarantee or whole-backend signoff follows.
- New `apps/desktop/src/petInteraction.ts`: full helper review. Changed-path
  review of `PetStage.tsx` and `viewModel.test.ts` for primary-button activation,
  cancelled/no-start gestures, and two-axis drag distance in `4dd121f`.
  Nine focused pet tests passed. Fresh `npm test` on `4dd121f`: **193 passed**;
  `npm run build`: successful TypeScript + Vite production frontend build
  (63 modules). Some tests inspect source contracts or server-rendered markup;
  they do not exercise native pointer routing, window dragging or installed UX.

No subagents, model calls, native input or runtime restarts in these passes.
`services/supervisor/src/pex_supervisor/loop.py` remains protected/uncommitted
and outside these repairs. New installed-build smoke, all-eight-pet visual
checks and remaining end-to-end specification gates are still open.

### Verification reference binding — 6 Sep

New source/test paths: `services/bridge/src/pex_bridge/verification_actions.py`
and `tests/unit/test_verification_action_binding.py`. Root reviewed both entire
new files; changed-path scope covers pipeline dispatch binding, supervisor prompt
contract and the additional handoff E2E regressions, not all of those existing
files. Independent review identified model-text authority leakage with an otherwise
valid reference; canonical locally generated text now replaces it for every form.
See [VERIFICATION_REFERENCE_REVIEW.md](VERIFICATION_REFERENCE_REVIEW.md) for live
failure provenance, final targeted gates and remaining live/clean-source limits.

The earlier fixture-ownership strict full clean `f529644` gate is complete:
3,718 passed / 27 skipped, zero failures/errors and no thread-warning recurrence.
This is not full-file audit completion or a full run of the newer probe repair.

### Handoff fixture resource ownership — 6 Sep

Changed-path review only: `tests/e2e/test_handoff_and_permissions.py` client
fixture and cleanup regression. Terra repaired a confirmed missing pipeline join
and partial-setup cleanup gap. Root and independent Terra reviewer checked
Pipeline/Store teardown ordering; the regression finishes real SQLite access
during presentation cancellation before Store closes. Root full affected-file
gate: 60 passed, thread warnings treated as errors; Ruff clean. The historical
full-suite warning was not reproduced in isolation, so its exact attribution
and elimination remain unproven pending a fresh clean-source full gate.

### Oversized selected command-output observations — 6 Sep

Root full-new-file review: `adapters/codex_output.py` and
`tests/unit/test_codex_output_withholding.py`. Root and Terra changed-path review:
`adapters/codex_shared.py` journal-before-route handoff and `adapters/codex.py`
unavailable-output normalization. Terra caught the nested alternate item identity
gap; fixed and tested. Framed bytes, bounded metadata, no inferred test success,
negative identities/envelopes, absent journal, duplicate ordering and subsequent
STOP are covered. Final combined five-file gate 204 passed, scoped
Ruff clean. These are not full-file approvals of existing adapters or a live proof.
See the checkpoint for the distinct pending clean-source/full/live gates.

### Literal PowerShell evidence and unrelated lifecycle isolation — 6 Sep

Changed-path review, not whole-file approval:

- `packages/protocol/src/pex_protocol/verification.py`: exact literal wrapper
  recognition, direct-command parser reuse, preserved targeted/full-suite scope;
  expansion, composition, quoted-executable and shell ambiguity rejected.
- `services/bridge/src/pex_bridge/adapters/codex_shared.py`: schema-minimal foreign
  lifecycle filtering after durable receive/freshness accounting, without feeding
  foreign events into selected-worker context or ignoring selected closure.
- Associated changed tests in `test_verification_protocol.py`, `test_shell_state.py`,
  `test_codex_shared_adapter.py`, `test_codex_pipeline_pump.py` and
  `test_codex_shared_transport.py`: root and Terra reviewers examined the new cases.

Independent review caught and repaired whitespace normalization in the foreign-ID
filter. A broader test run exposed an existing timeout fixture that timed out in
initialization rather than its intended written request; initialization now occurs
before applying the short request timeout, without relaxing production behavior.
Evidence: parser neighborhood 85 passed; official pump 23 passed; shared adapter 8
passed; final six-file transport/lifecycle/dispatch attribution gate 169 passed.
Production repairs: `7a41a24`, `5502539`; expanded regressions: `56be964`, `4d6dd60`.
Full clean-source Python gate and fresh live recapture are separate pending gates.
The protected operator-owned supervisor `loop.py` was not changed or included.
See [checkpoint](CHECKPOINT_2026_09_06.md) for exact failures and evidence limits.

### Fresh control snapshots and final effect validation — `e64270c`

Full new-test review: `test_codex_shared_read_snapshot.py`, `test_codex_control_snapshot.py`, `test_main_effect_live_revalidation.py`. Changed-path review: shared transport parser-boundary/read/routing/dispatch checks, coordinator control-only snapshot and Store main-effect check factoring/final validator. `attachment_review` independently approved transport and authored framed regressions; `transport_review` authored Store, then independently reproduced and approved the coordinator unknown/empty-type fix; main reviewed/integrated all owned paths. Final main 483 passed/18 complete files, no skips; six scoped Python paths Ruff/staged-whitespace clean. Source pushed with exact remote equality. [`Full evidence and limitations`](CONTROL_SNAPSHOT_REVIEW.md). No blanket full-file/whole-repository audit or shared-control activation follows.

### Production received-byte journal — `db98481`

Main full-new-file review: `codex_received_journal.py` and `test_codex_received_journal{,_attachment,_transport}.py`; changed-path review: `codex_shared.py`, `codex_shared_attach.py`, three existing transport/attachment test files and `.gitignore`. Independent `attachment_review` read the new files and production diffs, reproduced the foreign-WAL defect, then approved the preflight fix and reran the exact failure plus 32 new tests. Main final 456 passed/23 files, all nine scoped Python paths Ruff-clean and ten staged paths whitespace-clean, source pushed with remote equality. [`Complete bounded receipt`](RECEIVED_JOURNAL_REVIEW.md). This does not close the full repository audit, complete crash recovery or approve worker-control activation.

### Connection UI and inactive text control — `cd39913`, `03045b5`

Main read new `apps/desktop/src/{operatorRequest.ts,operatorRequest.test.ts,sharedConnection.ts,sharedConnection.test.ts,components/SharedConnectionPanel.tsx}`, both `apps/desktop/tests/connection-qa.{html,tsx}` fixtures and new `tests/unit/test_codex_shared_text_dispatch.py`. Changed-path review: App, Settings, package test script, and `codex_shared.py` dispatch/receive-routing/close/error changes. Independent review covered controller/mount/request contract and framed transport; reproduced findings were repaired. Main 154 desktop tests, TypeScript/frontend build, isolated rendered recovery, 406 backend tests/18 files. All 12 staged source/test paths passed whitespace checks; both Python paths passed Ruff. New-file/diff coverage is not whole-App/Settings/transport approval or a complete reinventory. [`Detailed evidence and limits`](CONNECTION_CONTROL_REVIEW.md).

### Owned subscription close — accepted `c15a2fc`

New `tests/unit/test_codex_subscription_close_ownership.py`: five cases, full new-file review by main and independent reviewer. Changed-path review: coordinator `_close_after_failed_resume` and its callers in `services/bridge/src/pex_bridge/adapters/codex_subscription.py`; held-close barrier/assertions in `tests/unit/test_codex_subscription.py`. Independent reviewer additionally checked actual shared transport revocation and bounded channel cleanup. Final main 355 passed/17 files; scoped Ruff/staged whitespace clean; source pushed with exact remote equality. This supersedes the separate-unaccepted-test wording below. No blanket coordinator/transport or whole-repository approval; exact failures, gates and limits are in [`WORKSPACE_CONTINUITY_REVIEW.md`](WORKSPACE_CONTINUITY_REVIEW.md).

### Post-attachment continuity and Ask invocation review — 5 Sep

Main reread all three specs, all new helper/test files, and changed production paths. Bounded owners independently reviewed Store, adapter/Pipeline/access, executor/evidence and real Ask paths. Large Store/Pipeline/App/Executor files received changed-path review, not blanket full-file approval. Reviewed source/API guide **`c0db453`** is pushed with exact remote equality; final main **1,016 passed/3 skipped across 56 files**, scoped Ruff for all 27 Python paths. Exact gates and reproduced late findings are in [`WORKSPACE_CONTINUITY_REVIEW.md`](WORKSPACE_CONTINUITY_REVIEW.md). No live product claim or exhaustive reinventory follows. The new subscription-close test belongs to a separate unaccepted repair.

New source files fully reviewed: `services/bridge/src/pex_bridge/workspace_access.py`, `services/supervisor/src/pex_supervisor/review_authority.py`.

New regression files fully read/reviewed by main and bounded owners: `tests/unit/test_workspace_access.py`, `test_workspace_continuity_pipeline.py`, `test_workspace_continuity_store_review.py`, `test_workspace_continuity_recovery_store.py`, `test_workspace_continuity_tools.py`, `test_workspace_continuity_executor.py`, `test_workspace_continuity_ask.py`, `test_workspace_main_dispatch.py`, `test_workspace_operator_handoff.py`, `test_workspace_ask_fallback.py`, `test_review_authority.py`.

Existing production changes reviewed: shared adapter typed loss handling; Store publication/metadata/continuity and effect-settlement branches; Pipeline snapshots/planner/main/direct-handoff/claim-verification; Executor new-effect checks; workspace binding's typed sample helper; supervisor evidence-tool wrappers; app Ask checks; actual answer selection; queued Ask Strands entry; HTTP fallback attempt checks. Existing observer lifecycle/retention/publication fixtures and four unbound overlay test stubs were changed to match the protected publication contract, without weakening negative assertions. Supervisor `loop.py` remains unowned and unapproved.

### Local-origin/workspace attachment addendum — 5 Sep

Source `f08ad80`; main final 26-file gate 545 passed/2 Windows symlink-permission skips. Main read the three specs and new source/test files; independent reviewers covered helper persistence/directory logic, manager integration and Store publication branches. Store review is changed-path only, not full-file approval. Reproduced failures and repair receipts are at the top of the handoff. API guide `docs/adapters/local-workspace-origin.md` was added and reviewed. This is not an exhaustive reinventory or live product approval.

New fully reviewed paths: `services/bridge/src/pex_bridge/local_workspace.py`, `local_origin_config.py`, `workspace_binding.py`; `tests/unit/test_local_workspace.py`, `test_local_origin_config.py`, `test_local_origin_review.py`, `test_workspace_attachment.py`, `test_workspace_attachment_review.py`, `test_workspace_publication.py`. Existing changed paths: `codex_shared_attach.py`, the workspace-publication branch/imports of `store.py`, and the explicit-origin fixture/earlier-rejection assertion in `test_codex_shared_attach.py`. Unowned supervisor `loop.py` is neither edited nor approved. Continuous workspace/evidence/action authority, installed runtime, desktop caller and full audit coverage remain open.

### Stream-loss retention addendum — 5 Sep

Main and bounded owners reviewed changes to `codex_subscription.py`, `codex_shared_adapter.py`, `codex_shared_attach.py`, `pipeline.py`, `store.py`, `test_codex_subscription.py` and the attachment fixture in `test_codex_shared_attach.py`. Existing large Pipeline/Store received changed-path review only. Independent review covered coordinator/Store and main adapter/Pipeline/wiring, including the reproduced and fixed 2,048-record reconciliation capacity defect. See the current handoff for integration/push evidence; live runtime and complete raw/crash coverage remain unproven.

New test paths (additions, not a refreshed exhaustive inventory):

- `tests/unit/test_codex_observation_retention.py`: full main and independent review; 12 real temporary-Store/Pipeline regressions for prefix loss, semantic suppression, retry, queue/cancellation, canonical replay and ownership.
- `tests/unit/test_observer_retention_store.py`: full owner/main review and independent Store review; 25 SQLite cases for record-only atomic retention, target/receipt/binding, controls, duplicate/collision/order and byte limits.
- `tests/unit/test_codex_reconciliation_retention.py`: full independent owner/main review; both real coordinator reconciliation drains (2,048 records), queue saturation and cancellation, with explicitly fake retention sink.

### Shared observer source and intent-authority addendum — 5 Sep

New paths below are additions to the historical inventory, not a fresh exhaustive count. Full module review by the transport/attachment owners and main's integration/diff review cover the bounded new shared source; existing huge app/pipeline/Store/Codex files received changed-path review, not whole-file approval. Independent reviewers reproduced recovery, false-status and partial-input authority bugs and reviewed their repairs. The final complete-file integration gate is in the current handoff. No live worker, provider, UI or complete-trajectory claim follows. Origin binding, lost batch prefixes, raw/durable capture and same-worker control remain open.

| New path | Bounded review scope |
| --- | --- |
| `services/bridge/src/pex_bridge/adapters/codex_shared.py` | Full transport owner and independent review; framing, RPC identity, protected paths, owned connector cleanup; installed runtime unproven |
| `services/bridge/src/pex_bridge/adapters/codex_subscription.py` | Full coordinator review; exact selection, history/live reconciliation, closure and runtime flags; prefix-loss limit explicit |
| `services/bridge/src/pex_bridge/adapters/codex_shared_adapter.py` | Main full read plus independent lifecycle/status review; bounded buffering, retry, witness-bound ingestion, no worker effects |
| `services/bridge/src/pex_bridge/codex_shared_attach.py` | Main and attachment owner full read; auth, expiry, CAS, cancellation and prior-pump recovery; origin gap retained |
| `tests/unit/test_codex_shared_transport.py` | Full transport review; fake process/protocol regressions and read-only native ACL probes |
| `tests/unit/test_codex_subscription.py` | Coordinator owner full review; fake selected worker and strict lifecycle/runtime cases |
| `tests/unit/test_codex_shared_adapter.py` | Main full read; actual pump with fake vendor and controlled sinks |
| `tests/unit/test_codex_shared_attach.py` | Owner full review; main reviewed CAS/recovery/cancellation regressions; authenticated API fixtures, real Store |
| `tests/unit/test_codex_attach_serialization.py` | Legacy owner full review; independent final compatibility run, no real worker spawn |
| `tests/unit/test_codex_user_content.py` | Main and content reviewer full read; exact content, uncertainty and upstream redaction |
| `tests/unit/test_codex_partial_intent.py` | Main and reviewer full read; real Store negative authority cases and complete-input positive controls |
| `tests/unit/test_observer_session_publication.py` | Main and Store reviewer full read; CAS, human-control retention, acceptance race and canonical projection |
| `tests/unit/test_observer_lifecycle_pipeline.py` | Main and lifecycle reviewer full read; real record-only disconnect and current-incarnation protection |
| `tests/unit/test_codex_shared_status_pipeline.py` | Main full read and independent runtime review; real Pipeline/Store state, activity and ordered batch projections |

Unowned `services/supervisor/src/pex_supervisor/loop.py` remains outside the reviewed source checkpoint.

### Durable dispatch authority addendum — 5 Sep

Main and independent credential reviewer reviewed the bounded `store.py` schema/migration, atomic event acceptance, main-effect claim, session-control revision and event-projection changes. Main fully read new `tests/unit/test_generic_dispatch_authority.py`; independent reviewer ran all 14 cases and approved the final diff. Pre-fix source loaded in memory reproduced stale grants, without changing the checkout or invoking external effects. Final integration/push receipt is in the current handoff. This is not full-file review of the large Store module or proof of transport concurrency safety.

Add the new authority test file to the next reconciled inventory. New shared Codex transport/coordinator files and their tests are separate agent WIP with incomplete main review/integration; do not count them as reviewed capabilities. The unowned `loop.py` change remains excluded.

### Provider/setup repair addendum — 5 Sep

Main and the independent credential reviewer fully read the new `apps/desktop/src/supervisorDraft.ts` and `supervisorDraft.test.ts`, and reviewed changed App/SettingsPage/viewModel-test/package wiring. Main and setup owner fully read `scripts/install.ps1` and new `tests/unit/test_source_setup_contract.py`; the setup owner fully read README, with main reviewing its changed setup/architecture text. Main reviewed the provider runtime-scope/mismatch patch and all new provider/route tests after independent reproduction; this does not equal whole-file approval of `providers.py` or `app.py`. Seven-file final gate: 147 passed/1 symlink skip; desktop: 97 checks/TypeScript. New `docs/CODEX_EXISTING_SESSION_AUDIT.md` records bounded Codex source/protocol review, not a live integration receipt.

The three newly added source/test paths in this cycle must be included when the full inventory is next reconciled. Counts below are historical snapshot/addendum counts, not a fresh exhaustive file inventory. The growing unknown `loop.py` changes are explicitly not reviewed or included in this checkpoint.

Five new paths after the original snapshot bring this ledger to **346 source/configuration paths**. This is not a refreshed exhaustive filesystem inventory; reconcile new files again before release. The initial domain audits recorded 49 full reads. Main and independent reviewers also reviewed the outcome/context/UI repair diffs; that is bounded changed-code review, not full-file approval for the large existing pipeline, Store, adapter or App modules. Remaining findings and actual UI/provider proof stay open in `SHIP_CHECKLIST.md`.

| New file | Review scope / result |
| --- | --- |
| `services/bridge/src/pex_bridge/adapters/opencode_outcomes.py` | FULL READ by main and harness owner; exact receipt/parent/scope checks; offline positive and adversarial coverage, not live proof |
| `services/bridge/src/pex_bridge/supervisor_context.py` | FULL READ by main and supervisor owner; re-read 9 September, repaired omitted decision scope in text-budget accounting. Regression admitted 27,000 vs 18,000 characters before fix; context/integration gate 15 passed, Ruff passed. Exact evidence observations remain separate. |
| `tests/unit/test_opencode_outcome_lineage.py` | FULL READ by harness owner; main reviewed terminal and attribution cases; offline fixtures only |
| `tests/unit/test_supervisor_context.py` | FULL READ by supervisor owner; main reviewed integration and pagination boundaries; no real model execution |
| `tests/unit/test_worker_outcome_attribution.py` | FULL READ by main and independent integration reviewer; generic false-credit and foreign-authority regressions |

## Original snapshot

| File | Audit responsibility | Fresh audit status |
| --- | --- | --- |
| `apps/desktop/package.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/scripts/build-sidecar.mjs` | UI / release | PENDING |
| `apps/desktop/scripts/record_submission_demo.py` | UI / release | REMOVED 11 Sep; stale browser-only recorder targeted retired controls and could not prove the packaged product |
| `apps/desktop/scripts/release-contract.mjs` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/scripts/release-contract.test.mjs` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/build.rs` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/capabilities/default.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/capabilities/pet.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/Cargo.toml` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/permissions/focus.toml` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/src/main.rs` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src-tauri/tauri.conf.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/App.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/AskPex.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/CommandDeck.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/GoalEditor.tsx` | UI / release | Full re-read 9 September; disabled fieldset while saving prevents edits being cleared by pending save completion. SSR regression failed before fix; 267 desktop tests and frontend build pass. Native layout/interaction remains unverified. |
| `apps/desktop/src/components/Inspector.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/PetStage.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/ProjectIdentityPanel.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/components/SettingsPage.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/decisionContract.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/main.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/pets/atlas.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/pets/atlasMath.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/pets/drift/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/ember/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/ledger/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/mesh/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/nudge/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/pex/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/quiet/pet.json` | UI / release | PENDING |
| `apps/desktop/src/pets/release-manifest.json` | UI / release | PENDING |
| `apps/desktop/src/pets/types.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/pets/von/pet.json` | UI / release | PENDING |
| `apps/desktop/src/releasePet.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/types.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/viewModel.test.ts` | UI / release | PENDING |
| `apps/desktop/src/viewModel.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/src/vite-env.d.ts` | UI / release | PENDING |
| `apps/desktop/tsconfig.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/vite.config.ts` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `benchmarks/boundary.py` | Harness / integrity | PENDING |
| `benchmarks/cursor_capture.py` | Harness / integrity | PENDING |
| `benchmarks/cursor_isolated_stop.py` | Harness / integrity | PENDING |
| `benchmarks/evaluator.py` | Harness / integrity | PENDING |
| `benchmarks/four_arm.py` | Harness / integrity | PENDING |
| `benchmarks/manifest.yaml` | Harness / integrity | PENDING |
| `benchmarks/pex_attach.py` | Harness / integrity | Partial 9 September outcome-path audit: missing baseline no longer earns helpful-intervention credit; literal False -> True required. Three regressions failed before fix; outcome/report gate 10 passed. Full-file audit remains pending. |
| `benchmarks/pex_supervisor_process.py` | Harness / integrity | PENDING |
| `benchmarks/report.py` | Harness / integrity | PENDING |
| `benchmarks/runner.py` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_001_premature_stop/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_002_drift/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_003_permission_spam/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_004_false_claim/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_005_handoff/metadata.yaml` | Harness / integrity | PENDING |
| `deploy/agentcore/preflight.py` | Backend / release cross-review | FULL READ by main 11 Sep; bounded read-only subprocesses, AWS/CLI/CDK/Docker/ARM64/image/secret-ignore/ARN-region gates and separate action authorization reviewed; mocked matrix passes 16/16, no AWS call |
| `docker-compose.yml` | Backend / release cross-review | PENDING |
| `fixtures/demo/dataset_before_eval.json` | Backend / release cross-review | PENDING |
| `fixtures/demo/premature_stop_eval.json` | Backend / release cross-review | PENDING |
| `integrations/claude-hook/settings.fragment.json` | Harness / integrity | PENDING |
| `integrations/cursor-hook/hooks.json` | Harness / integrity | PENDING |
| `integrations/cursor-hook/install.py` | Harness / integrity | PENDING |
| `integrations/cursor-hook/pex_cursor_hook.py` | Harness / integrity | PENDING |
| `integrations/cursor-hook/pex_cursor_observe.py` | Harness / integrity | PENDING |
| `integrations/hermes-plugin/pex_plugin.py` | Harness / integrity | PENDING |
| `integrations/hooks/pex_hook.py` | Harness / integrity | PENDING |
| `integrations/opencode-plugin/pex-plugin.js` | Harness / integrity | FULL READ by main 11 Sep; loopback/auth/request-response/JSON/cache bounds and fail-open worker behavior reviewed; no new defect found |
| `integrations/qwen-hook/settings.fragment.json` | Harness / integrity | PENDING |
| `packages/protocol-ts/src/index.ts` | Backend / release cross-review | PENDING |
| `packages/protocol/pyproject.toml` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/__init__.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/actions.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/capabilities.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/context.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/enums.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/fingerprint.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/goal.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/intervention.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/overlay.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/project_identity.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/redaction.py` | Backend / release cross-review | PENDING |
| `packages/protocol/src/pex_protocol/session.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/supervisor.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `packages/protocol/src/pex_protocol/verification.py` | Backend / release cross-review | PENDING |
| `pyproject.toml` | Backend / release cross-review | PENDING |
| `rust-toolchain.toml` | Backend / release cross-review | PENDING |
| `scripts/install.ps1` | Backend / release cross-review | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `scripts/pet_atlas_runtime_contract.py` | Backend / release cross-review | PENDING |
| `services/bridge/pyproject.toml` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/__main__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/adapters/__init__.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/acp_client.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/acp_harness.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/attach.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/base.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/claude_code.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/codex_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/codex.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/connect.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_hooks.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor_inbox.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/cursor.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/desktop.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/devin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/discover.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/fleet.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_bot.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_build_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/grok_build.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/hermes_bin.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/http_json.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/opencode.py` | Harness / integrity | FULL READ by main 11 Sep; session/workspace binding, delivery uncertainty, permissions, overlays, SSE lineage/gaps and retry pump reviewed; no new defect found |
| `services/bridge/src/pex_bridge/adapters/qwen.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/strict_json.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/synthetic.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/winfocus.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/agentcore.py` | Backend / release cross-review | FULL READ 11 Sep; 183-test AgentCore gate passed; live deployment remains open |
| `services/bridge/src/pex_bridge/app.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/ask.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/benchmark_public.py` | Backend / release cross-review | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/bus.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/channels.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/claims.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/config.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/context/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/context/health.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/context/mesh.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/cursor_delivery.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/decision_delivery.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/decisions.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/deep_links.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/demo.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/executor.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/fingerprints.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/handoff_views.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/hook_auth.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/intent.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/ledger.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/main.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/mcp_auth.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/mcp_server.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/observe.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/origin_guard.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/overlay_runtime.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/atlas.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/hatch_store.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/hatch.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pets/imagegen.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/pipeline.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/policy/__init__.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/policy/engine.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/request_limits.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/scoring.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/bridge/src/pex_bridge/secrets.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/shell_state.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/speculative.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/store.py` | Backend / release cross-review | PENDING |
| `services/bridge/src/pex_bridge/supervisor_config.py` | Backend / release cross-review | PENDING |
| `services/supervisor/pyproject.toml` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/__init__.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/ask_review.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/background.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/catalog.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/drift.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/evidence_tools.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/supervisor/src/pex_supervisor/inspect_http.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/loop.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/supervisor/src/pex_supervisor/planner.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `services/supervisor/src/pex_supervisor/providers.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/public_task.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/runtime.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/search.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/verify.py` | Backend / release cross-review | PENDING |
| `services/supervisor/src/pex_supervisor/workspace.py` | Backend / release cross-review | FULL READ backend 5 Sep; findings open; later edits need re-review |
| `tests/__init__.py` | Test cross-review | PENDING |
| `tests/chaos/test_malformed_events.py` | Test cross-review | PENDING |
| `tests/conftest.py` | Test cross-review | Read fully 9 September: offline supervisor/desktop defaults reviewed; fixtures are not a substitute for explicit live authorization. Unchanged. |
| `tests/contract/__init__.py` | Test cross-review | PENDING |
| `tests/contract/codex_live_proof.py` | Test cross-review | PENDING |
| `tests/contract/live_gate.py` | Test cross-review | Read fully 9 September: requires every named flag to equal `1`; unchanged. Static inventory enforces exact nonempty flag lists at live test entry. |
| `tests/contract/test_authorization_inventory.py` | Test cross-review | Reviewed 9 September: removed AgentCore substring fallback; require direct literal shared-gate calls, reject empty/dynamic/keyword calls. Offline inventory: 3 passed; scoped Ruff passed. AST checks do not prove runtime isolation or authorization outside these test entry points. |
| `tests/contract/test_cursor_capture_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_delivery_ack_hook.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_prompt_policy.py` | Test cross-review | PENDING |
| `tests/contract/test_intent_guardrails.py` | Test cross-review | PENDING |
| `tests/contract/test_live_agentcore.py` | Test cross-review | Read fully 9 September; standardized first-statement authorization to shared helper. Static inventory and lint passed. Live test NOT executed; no deployment or inference proof claimed. |
| `tests/contract/test_live_claude_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex_pump.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex.py` | Test cross-review | PENDING |
| `tests/contract/test_live_cursor_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_devin_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_grok_build_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_hermes_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_kimi_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_omp_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_opencode_stop.py` | Test cross-review | FULL READ by main 11 Sep; explicitly authorized real-supervisor/in-memory-transport contract, completed-inference requirement and probe-owned cleanup reviewed; correctly disclaims real-worker recovery proof |
| `tests/contract/test_live_opencode.py` | Test cross-review | FULL READ by main 11 Sep; explicit live authorization, bounded Deep wait and owned transport cleanup; model-free production run passed 1/1 |
| `tests/contract/test_live_qwen_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_supervisor.py` | Test cross-review | PENDING |
| `tests/contract/test_supervisor_settings.py` | Test cross-review | PENDING |
| `tests/e2e/test_ask_canonical.py` | Test cross-review | PENDING |
| `tests/e2e/test_decision_resolution.py` | Test cross-review | PENDING |
| `tests/e2e/test_direct_message_durability.py` | Test cross-review | PENDING |
| `tests/e2e/test_goal_control_operation_routes.py` | Test cross-review | PENDING |
| `tests/e2e/test_goal_lifecycle.py` | Test cross-review | PENDING |
| `tests/e2e/test_handoff_and_permissions.py` | Test cross-review | PENDING |
| `tests/e2e/test_handoff_timeout_safety.py` | Test cross-review | PENDING |
| `tests/e2e/test_hatch_operator_api.py` | Test cross-review | PENDING |
| `tests/e2e/test_hook_credentials.py` | Test cross-review | PENDING |
| `tests/e2e/test_lifecycle_decision_resolution.py` | Test cross-review | PENDING |
| `tests/e2e/test_m0_roundtrip.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_adversarial_boundary.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_credentials.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_safety_contract.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_server.py` | Test cross-review | PENDING |
| `tests/e2e/test_mcp_verify_claim_atomic.py` | Test cross-review | PENDING |
| `tests/e2e/test_overlay_revert_operator_auth.py` | Test cross-review | PENDING |
| `tests/e2e/test_project_identity_operator_api.py` | Test cross-review | PENDING |
| `tests/e2e/test_recovery_stop_loop.py` | Test cross-review | PENDING |
| `tests/e2e/test_remote_channels.py` | Test cross-review | PENDING |
| `tests/e2e/test_speculative_execution.py` | Test cross-review | PENDING |
| `tests/integration/test_strands_supervisor.py` | Test cross-review | PENDING |
| `tests/unit/test_acp_cursor.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_capabilities.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_deep_audit.py` | Test cross-review | PENDING |
| `tests/unit/test_adapter_protocol_safety.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_client.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_pipeline.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_preflight.py` | Test cross-review | PENDING |
| `tests/unit/test_agentcore_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_artifact_project_bindings.py` | Test cross-review | PENDING |
| `tests/unit/test_ask_review.py` | Test cross-review | PENDING |
| `tests/unit/test_ask.py` | Test cross-review | PENDING |
| `tests/unit/test_attach_security.py` | Test cross-review | PENDING |
| `tests/unit/test_attention_metrics.py` | Test cross-review | PENDING |
| `tests/unit/test_audit_invariants.py` | Test cross-review | PENDING |
| `tests/unit/test_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_authority_consumer_wiring.py` | Test cross-review | PENDING |
| `tests/unit/test_background.py` | Test cross-review | PENDING |
| `tests/unit/test_benchmark_execution_safety.py` | Test cross-review | PENDING |
| `tests/unit/test_benchmark_public.py` | Test cross-review | PENDING |
| `tests/unit/test_broadcast_serialization.py` | Test cross-review | PENDING |
| `tests/unit/test_channels.py` | Test cross-review | PENDING |
| `tests/unit/test_claim_verification_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_claims_and_shell_state.py` | Test cross-review | PENDING |
| `tests/unit/test_claims.py` | Test cross-review | PENDING |
| `tests/unit/test_cleanup_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_cleanup_restore_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_codex_live_proof.py` | Test cross-review | PENDING |
| `tests/unit/test_codex_pipeline_pump.py` | Test cross-review | PENDING |
| `tests/unit/test_config_security.py` | Test cross-review | PENDING |
| `tests/unit/test_context_handoff_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_context_health.py` | Test cross-review | PENDING |
| `tests/unit/test_context_mesh.py` | Test cross-review | PENDING |
| `tests/unit/test_control_file_bounds.py` | Test cross-review | PENDING |
| `tests/unit/test_credential_project_bindings.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_capture.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_delivery_store.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_followup_receipt.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_hook_preparation.py` | Test cross-review | PENDING |
| `tests/unit/test_cursor_stop_response_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_deep_links.py` | Test cross-review | PENDING |
| `tests/unit/test_demo_security.py` | Test cross-review | PENDING |
| `tests/unit/test_drift.py` | Test cross-review | PENDING |
| `tests/unit/test_event_bus.py` | Test cross-review | PENDING |
| `tests/unit/test_event_processing_pipeline.py` | Test cross-review | PENDING |
| `tests/unit/test_event_processing_store.py` | Test cross-review | PENDING |
| `tests/unit/test_event_publications.py` | Test cross-review | PENDING |
| `tests/unit/test_evidence_tools.py` | Test cross-review | PENDING |
| `tests/unit/test_existing_sessions.py` | Test cross-review | PENDING |
| `tests/unit/test_fleet_pets_codex.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_control_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_intent_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_intent_semantics.py` | Test cross-review | PENDING |
| `tests/unit/test_goal_store_transaction.py` | Test cross-review | PENDING |
| `tests/unit/test_handoff_assimilation_paths.py` | Test cross-review | PENDING |
| `tests/unit/test_hatch_durability.py` | Test cross-review | PENDING |
| `tests/unit/test_hatch_imagegen_security.py` | Test cross-review | PENDING |
| `tests/unit/test_host_guard.py` | Test cross-review | PENDING |
| `tests/unit/test_human_decision_delivery.py` | Test cross-review | PENDING |
| `tests/unit/test_human_decision_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_inspect_http.py` | Test cross-review | PENDING |
| `tests/unit/test_intent_guardrails.py` | Test cross-review | PENDING |
| `tests/unit/test_intervention_authority_consumers.py` | Test cross-review | PENDING |
| `tests/unit/test_leakage.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_actions.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_resource_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_lifecycle_restore_operations.py` | Test cross-review | PENDING |
| `tests/unit/test_mcp_auth_middleware.py` | Test cross-review | PENDING |
| `tests/unit/test_mcp_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_named_hook_deadline.py` | Test cross-review | PENDING |
| `tests/unit/test_observe_security.py` | Test cross-review | PENDING |
| `tests/unit/test_opencode_fork.py` | Test cross-review | FULL READ by main 11 Sep; official fork endpoint, child identity/project binding, exact context injection and detached refusal pass 2/2 |
| `tests/unit/test_opencode_pipeline_pump.py` | Test cross-review | FULL READ by main 11 Sep; event-loop responsiveness, bounded discovery, exact retry, gap and durable-journal idempotency coverage passes 12/12 |
| `tests/unit/test_operator_effects.py` | Test cross-review | PENDING |
| `tests/unit/test_operator_handoff_effects.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_executor_ledger.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_lifecycle.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_pipeline_recovery.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_overlay_store_authority.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_atlas_runtime_contract.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_hatch.py` | Test cross-review | PENDING |
| `tests/unit/test_pet_snapshot.py` | Test cross-review | PENDING |
| `tests/unit/test_pexbench.py` | Test cross-review | PENDING |
| `tests/unit/test_pipeline_serialization.py` | Test cross-review | PENDING |
| `tests/unit/test_pipeline_session_merge.py` | Test cross-review | PENDING |
| `tests/unit/test_planner.py` | Test cross-review | PENDING |
| `tests/unit/test_policy_scoring.py` | Test cross-review | PENDING |
| `tests/unit/test_progress_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_project_identity_store.py` | Test cross-review | PENDING |
| `tests/unit/test_project_identity.py` | Test cross-review | PENDING |
| `tests/unit/test_providers.py` | Test cross-review | PENDING |
| `tests/unit/test_public_task.py` | Test cross-review | PENDING |
| `tests/unit/test_request_limits.py` | Test cross-review | PENDING |
| `tests/unit/test_resolution_dispatch_identity.py` | Test cross-review | PENDING |
| `tests/unit/test_scoring.py` | Test cross-review | PENDING |
| `tests/unit/test_search.py` | Test cross-review | PENDING |
| `tests/unit/test_session_control_transactions.py` | Test cross-review | PENDING |
| `tests/unit/test_shell_state.py` | Test cross-review | PENDING |
| `tests/unit/test_speculative.py` | Test cross-review | PENDING |
| `tests/unit/test_store_artifact_transactions.py` | Test cross-review | PENDING |
| `tests/unit/test_store_audit_outbox.py` | Test cross-review | PENDING |
| `tests/unit/test_store_canonical_queries.py` | Test cross-review | PENDING |
| `tests/unit/test_store_fingerprints.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_decision.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_integrity.py` | Test cross-review | PENDING |
| `tests/unit/test_store_mcp_verify_claim.py` | Test cross-review | PENDING |
| `tests/unit/test_strands_runtime.py` | Test cross-review | PENDING |
| `tests/unit/test_supervisor_config.py` | Test cross-review | PENDING |
| `tests/unit/test_supervisor_loop.py` | Test cross-review | PENDING |
| `tests/unit/test_verification_protocol.py` | Test cross-review | PENDING |
| `tests/unit/test_verify.py` | Test cross-review | PENDING |
| `tests/unit/test_websocket_auth.py` | Test cross-review | PENDING |
| `tests/unit/test_worker_hook_credentials.py` | Test cross-review | PENDING |
| `tests/unit/test_workspace_inspect.py` | Test cross-review | PENDING |

## 8 September compact Home focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` compact route | REVIEWED / REPAIRED | Saved native Home capture plus bounded source review found duplicate first-run/recovery presentation. Setup now owns onboarding copy; unavailable setup hides only redundant Home notices. |
| `apps/desktop/src/supervisorDraft.test.ts` Home wiring contract | REVIEWED / EXTENDED | Negative failed on old `status={homeStatus}` wiring; post-fix focused test passed. |
| `apps/desktop/src/firstRun.ts` and adjacent state semantics | REVIEWED / NO CHANGE | Existing unavailable, connect-worker, set-goal, paused and operational precedence remains correct; adjacent three-file gate passed 110/110. |

The complete desktop command also passed 251/251 and TypeScript passed. Two transient Vite
port-24678 diagnostics left no listener immediately after the run. This is not a review of
all desktop code and is not current native visual evidence.

## 8 September Codex idle discovery focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/adapters/codex.py` pump cadence | REVIEWED / REPAIRED | Event wake remains immediate; idle `thread/list` refresh uses a tested 5-second delay instead of an inline 1-second loop. |
| `tests/unit/test_fleet_pets_codex.py` cadence contract | REVIEWED / EXTENDED | Import/contract failed before implementation; focused test and complete three-file adapter gate passed. |

The three-file gate passed 116/116 in 30.86 seconds and Ruff was clean. This does not
establish measured runtime CPU or complete review of Codex adapter behavior.

## 8 September desktop pet transport focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` pet transport effect | REVIEWED / REPAIRED | Authenticated snapshots now establish canonical freshness; malformed/closed sockets recover immediately; steady HTTP reconciliation is 30 seconds. |
| `apps/desktop/src/releasePet.test.ts` lifecycle/resource contract | REVIEWED / EXTENDED | Updated contract failed on the former four-second loop and passed after event-first wiring. |

Complete desktop tests passed 251/251 and TypeScript passed. Native CPU and failure recovery
remain unmeasured after this source change.

## 8 September Codex process-inventory focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/adapters/codex.py` desktop observation | REVIEWED / REPAIRED | Observe tile is created once at transport attachment; recurring `thread/list` calls opt out of process inventory. |
| `tests/unit/test_fleet_pets_codex.py` repeated-refresh contract | REVIEWED / EXTENDED | Forced at least three list refreshes and required exactly one inventory call; existing desktop-thread isolation remained green. |

The first zero-inventory draft failed broader compatibility and was corrected before commit.
Final three-file adapter gate passed 117/117; this is not native CPU evidence.

## 8 September attached-goal evidence transport focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` goal-evidence effect and event socket | REVIEWED / REPAIRED | Valid durable event pages wake one coalesced decisions/completion refresh; fallback cadence is 30 seconds; cleanup clears and aborts old-goal work. |
| `apps/desktop/src/readBudget.test.ts` source/resource contract | REVIEWED / EXTENDED | Negative contract rejected the prior four-second poll and binds event wake, coalescing, cancellation, and reconciliation wiring. |

Focused desktop coverage passed 125/125 and TypeScript passed. Native responsiveness and
resource use remain unmeasured after this source change.

## 8 September transparent pet compositor focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/styles.css` overlay sprite motion | REVIEWED / REPAIRED | Transparent always-on-top overlay suppresses the redundant infinite CSS transform while the timed atlas animation remains. |
| `apps/desktop/src/releasePet.test.ts` overlay resource contract | REVIEWED / EXTENDED | Negative contract failed before the override and binds both compositor restraint and retained atlas timing. |

Focused pet lifecycle/resource coverage passed 10/10; complete desktop coverage passed
252/252 and TypeScript exited 0. No native GPU/CPU measurement exists.

## 8 September hidden pet reader lifecycle focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` overlay activity boundary | REVIEWED / REPAIRED | Durable pet visibility now joins page visibility in gating the socket and pet/goal readers; inactive state resets canonical authority. |
| `apps/desktop/src/releasePet.test.ts` hidden reader contract | REVIEWED / EXTENDED | Negative contract rejected visibility-only gating and binds socket, poll, reset, and reactivation wiring. |

One stale adjacent source assertion failed the first complete run and was corrected to bind
the stronger lifecycle boundary. Final adjacent coverage passed 43/43, complete desktop
coverage passed 252/252, and TypeScript exited 0. Native Tauri lifecycle is unmeasured.

## 8 September native identity-monitor focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src-tauri/src/main.rs` verified identity monitor | REVIEWED / REPAIRED | Fallback cadence is two seconds and five misses; nominal 10-second loss boundary, token proof, loopback restriction, timeout, and fail-closed transition remain. |
| `apps/desktop/src/startupRecovery.test.ts` cross-language cadence contract | REVIEWED / EXTENDED | Negative contract rejected the prior one-second loop and binds interval, threshold, nominal boundary, and exact monitor use. |

The first Rust compile caught a missing test-module import and was repaired. Named native test
and all 17 Rust tests passed; complete desktop 253/253 and TypeScript passed. Runtime unmeasured.

## 8 September Inspector discovery-cadence focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` Inspector detail reader | REVIEWED / REPAIRED | Full harness discovery follows the existing slow tick; lightweight detail stays responsive and prior inventory is retained. |
| `apps/desktop/src/readBudget.test.ts` discovery cadence contract | REVIEWED / EXTENDED | Negative contract rejects an unconditional `/v1/discover` request and binds it to `includeDeck`. |
| `services/bridge/src/pex_bridge/adapters/discover.py` discovery cost | REVIEWED / UNCHANGED | Confirmed one desktop process inventory, four loopback probes, and CLI resolution per request; it does not refresh the supervisor pipeline. |

Focused read-budget tests passed 23/23, complete desktop tests passed 254/254, and TypeScript
exited 0. Native resource behavior remains unmeasured because PEX stayed closed.

## 8 September handoff-assimilation cadence focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` handoff status reader | REVIEWED / REPAIRED | Fan-out is independent from core detail, event-first, coalesced, 30-second reconciled, identity-guarded, and cancelled with the view. |
| `apps/desktop/src/readBudget.test.ts` handoff scheduling contract | REVIEWED / REPLACED | Rejects the old core-blocking reader and binds event wake, slow reconciliation, changed-ID refresh, and stale-key rejection. |

The negative contract failed on the old code. Focused tests passed 23/23, adjacent read/view
coverage passed 93/93, complete desktop tests passed 254/254, and TypeScript exited 0. The
history page remains capped at 200 and each fan-out batch remains four-concurrent and bounded.
Native request counts and batch latency are still unmeasured.

## 8 September benchmark-summary I/O focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/app.py` `/v1/bench/runs` | REVIEWED / REPAIRED | Synchronous file and JSON work is dispatched through `run_in_threadpool` instead of blocking the request event loop. |
| `tests/unit/test_benchmark_public.py` route execution contract | REVIEWED / EXTENDED | Records request and loader thread IDs and rejects same-thread execution. |
| `apps/desktop/src/App.tsx` benchmark reader | REVIEWED / REPAIRED | Summary follows the existing slow tick and retains the last validated result when skipped. |
| `apps/desktop/src/readBudget.test.ts` slow-reader contract | REVIEWED / EXTENDED | Rejects eight-second benchmark artifact reads alongside process discovery. |

Both negative contracts failed before the changes. Backend 16/16, desktop focused 23/23,
desktop complete 254/254, scoped Ruff, and TypeScript passed. Native I/O timing is unmeasured.

## 8 September project-identity reader focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` conflict-summary reader | REVIEWED / REPAIRED | Valid event pages wake a coalesced reader; unchanged state reconciles at 30 seconds with abort and sequence guards. |
| `apps/desktop/src/App.tsx` selected identity-status reader | REVIEWED / REPAIRED | Active Decisions status uses the same event-first boundary while preserving selection scope, pagination, and explicit resolution refresh. |
| `apps/desktop/src/readBudget.test.ts` lifecycle contract | REVIEWED / EXTENDED | Binds both readers to owned abort controllers and cleanup. |
| `apps/desktop/src/viewModel.test.ts` identity-flow contract | REVIEWED / EXTENDED | Binds event wakes, coalescing, 30-second reconciliation, and active-view scope. |

The negative adjacent run failed both new contracts on the old implementation. Final adjacent
coverage passed 93/93, complete desktop passed 254/254, and TypeScript exited 0. Native event
latency and database request counts remain unmeasured.

## 8 September canonical detail scheduler focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` detail scheduler | REVIEWED / REPAIRED | Core context/history/attention reads wake from committed event pages; one 32-second full pass retains Deck/discovery/benchmark and cannot be lost behind an active core read. |
| `apps/desktop/src/App.tsx` effect lifetime | REVIEWED / REPAIRED | First-load state and abort cleanup remain; unrelated pet last-action identity no longer restarts the full reader. |
| `apps/desktop/src/readBudget.test.ts` detail cadence contract | REVIEWED / EXTENDED | Rejects the eight-second tick loop and binds event wake, coalescing, slow-pass carry, 32-second reconciliation, and cancellation. |

Negative contracts failed on the old scheduler. Focused coverage passed 24/24, adjacent
read/view-model coverage passed 94/94, complete desktop passed 255/255, and TypeScript exited
0. Native request counts, latency, and resource use remain unmeasured.

## 8 September event-socket cadence focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/app.py` caught-up ledger tail | REVIEWED / REPAIRED | Missed-hint recovery uses the 15-second heartbeat boundary; process-local commits still wake the durable read immediately. |
| `tests/unit/test_websocket_auth.py` cadence/wake/lifetime contract | REVIEWED / EXTENDED | Rejects recovery polling faster than heartbeat while existing behavior checks immediate wake, auth, and disconnect cleanup. |
| `tests/unit/test_event_publications.py` and `test_broadcast_serialization.py` | REVIEWED / UNCHANGED | Durable ordering/gap and bounded publication serialization remain green. |

The old 5-second recovery constant failed the new contract. Focused socket tests passed 5/5,
adjacent publication coverage passed 17/17, and scoped Ruff passed. Native SQLite timing and
multi-window resource behavior are unmeasured.

## 8 September Settings activity-poll focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` base/settings readers | REVIEWED / REPAIRED | Expensive goals/catalog reads are independent from rejection health and hatch progress; all have view cancellation and request-generation guards. |
| `apps/desktop/src/readBudget.test.ts` Settings cadence contract | REVIEWED / EXTENDED | Rejects the coupled eight-second base loop and binds idle/active intervals plus independent reader lifetime. |
| `apps/desktop/src/viewModel.test.ts` rejection-health contract | REVIEWED / EXTENDED | Scopes fail-closed rejection state to its dedicated reader instead of matching an unrelated catch block. |

The old implementation failed both new lifecycle assertions. Focused read/view-model coverage
passed 95/95, complete desktop passed 256/256, and TypeScript exited 0. Inactive Settings source
scheduling falls from 30 to 8 endpoint reads per minute. Native request counts, atlas-cache
miss cost, and freeze impact remain unmeasured.

## 8 September Inspector loading-ownership focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/App.tsx` detail request completion | REVIEWED / REPAIRED | The newest accepted response clears loading regardless of which request enabled it; sequence guards still reject stale publication. |
| `apps/desktop/src/readBudget.test.ts` loading ownership contract | REVIEWED / EXTENDED | Rejects conditional-only loading release after a superseding non-loading refresh. |

The new contract failed on the prior conditional release. Focused coverage passed 26/26,
complete desktop passed 257/257, and TypeScript exited 0. Native visual behavior remains
unmeasured after the freeze incident.

## 8 September eight-pet release evidence review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/pets/{pex,ledger,mesh,nudge,drift,quiet,ember,von}` | REVIEWED / UNCHANGED | Exactly eight v2 manifests; project fleet gate and eight current skill validators exit 0; main inspected every current atlas without finding a static blocker. |
| `apps/desktop/src/pets/release-manifest.json` | REVIEWED / CURRENT | Hashes bind every current manifest/spritesheet and the structural/visual evidence files. |
| `apps/desktop/src/pets/release-evidence/structural.json` | REVIEWED / CURRENT | Binds geometry, 74 contract cells, transparent unused cells, neutral copy, and zero hidden RGB residue for each current atlas. |
| `apps/desktop/src/pets/release-evidence/neutral-repair.json` | REVIEWED / CURRENT | Proves standard animation pixels were unchanged while the required neutral cell was copied. |
| `apps/desktop/src/pets/release-evidence/independent-reviews.json` | REVIEWED / CURRENT BINDING | Three archived independent blind direction passes bind each current direction-cell hash root. |
| `apps/desktop/src-tauri/binaries/pex-sidecars-x86_64-pc-windows-msvc.json` and three executables | REVIEWED / STALE SOURCE | All binaries exist and match their stamp; the 6 September source fingerprint predates current changes, so rebuild/preflight remains open. |

No pet or binary was changed. This closes current atlas/metadata/static evidence, not native
animation/interaction or current release packaging.

## 8 September large-history projection focused review

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/store.py` recent/through-event authority readers | REVIEWED / REPAIRED | Reuses only transaction-local live-project results; distinct identities still receive one check and later requests revalidate from a fresh transaction. |
| `tests/unit/test_event_processing_store.py` | REVIEWED / EXTENDED | Proves two same-project events require one authority comparison for both bounded read variants while returning the same ordered events. |
| Real default `~/.pex/pex.sqlite` | READ-ONLY PROFILE EVIDENCE | 117.65 MiB, 19,079 events; largest session 9,032 events / 46.57 MiB event JSON. No data changed. |

Focused identity coverage passed 3/3; event-store/current-projection/pet-snapshot coverage passed
58/58; scoped Ruff and diff checks passed. The former maximum was one initial comparison plus
one per returned event (121 for a 120-row page); the repaired same-project case uses one. Native
SQLite timing and whole-machine freeze resolution remain open.

## 8 September native-profile ownership review

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src-tauri/src/main.rs` owned-sidecar environment | REVIEWED / REPAIRED | Resolves OS home through Tauri and pins `PEX_HOME=~/.pex` plus `PEX_DB_PATH=~/.pex/pex.sqlite`; loopback/auth/token/parent ownership remains explicit. |
| `apps/desktop/src/startupRecovery.test.ts` | REVIEWED / EXTENDED | Source contract rejects an inherited ambient profile path and binds both explicit sidecar variables. |
| Real `~/.pex/contest-goal` profile | READ-ONLY RISK EVIDENCE | 154.89 MiB database + 226.41 MiB WAL; `event_effects` 118.06 MiB. Incident environment unavailable, so causality remains unproven. |

Focused startup tests passed 15/15, Rust passed 18/18, complete desktop contracts passed 258/258,
TypeScript exited 0, and Rust formatting passed. No PEX process or database mutation occurred.
Current-source sidecar rebuild and bounded native resource proof remain open.

## 11 September retired eight-pet release validator cleanup

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/scripts/build-sidecar.mjs` | REVIEWED / REPAIRED | Removed 329 unreachable lines from the retired schema-2/eight-pet validator. The invoked schema-4 compact validator remains authoritative for the bundled `pex`, `von` fleet; the archived eight-pet review lineage remains intentionally retained as provenance and is not bundled. |
| `apps/desktop/scripts/release-contract.test.mjs` | REVIEWED / EXTENDED | Source contract requires exactly one current validator definition and one invocation, and rejects restoration of the retired validator or its obsolete eight-pet error text. |

`node --check scripts/build-sidecar.mjs` and the focused 14-test release-contract suite
passed after the deletion. Complete desktop tests, the frontend build, and the two-pet
validator are rerun before this batch is pushed. This cleanup changes no pet assets,
runtime profile, credentials, package artifact, or historical receipt.

## 11 September unreachable hatch frontend cleanup

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/src/viewModel.ts` | REVIEWED / REPAIRED | Removed the unused billable base-candidate disclosures, attempt state, idempotency builder, response matcher, and key generator. No production caller existed after the two-pet Settings cut. |
| `apps/desktop/src/types.ts` | REVIEWED / REPAIRED | Removed the unused hatch job, generation request, and generation-capability DTOs. Catalog source compatibility remains because old imported metadata can still be read without becoming a visible roster. |
| `apps/desktop/src/viewModel.test.ts` | REVIEWED / REPAIRED | Removed tests for the retired workflow and extended the two-pet source contract to reject reintroduction of hatch helpers and DTOs. |

The focused view-model suite passed 76/76. The complete desktop suite passed 289
tests with one intentional Windows symlink-permission skip, and the TypeScript/Vite
build passed with 69 transformed modules. An initial ad-hoc invocation using an
uninstalled `tsx` loader failed before test collection; the repository's native
Node 24 command was then used and passed. No backend compatibility route, pet asset,
credential, runtime profile, or package artifact changed.

## 11 September retired hatch startup detachment

| Path | Review result | Evidence |
| --- | --- | --- |
| `services/bridge/src/pex_bridge/app.py` | REVIEWED / REPAIRED | Removed the retired hatch package import, per-launch SQLite registry construction, task ledger, task tracker, and shutdown cleanup from the active bridge. Disabled compatibility reads now return an empty job list/404 without opening hatch storage; capability and mutation routes remain explicitly disabled. |
| `tests/e2e/test_hatch_operator_api.py` | REVIEWED / REPAIRED | Removed obsolete state injection while preserving authentication, strict request validation, zero-provider-call, disabled capability, and empty-history contracts. |
| `tests/unit/test_two_pet_scope.py` | REVIEWED / EXTENDED | Source contract rejects restoration of `HatchRegistry`, `self.hatch`, or `hatch_tasks` in the active bridge. |

An isolated `python -I` import proved `pex_bridge.pets.hatch`, `imagegen`, and
`hatch_store` were absent from `sys.modules` after importing the bridge app. Focused
tests passed 7/7; the broader app/pet/HTTP set passed 111/111 with the pinned Rust
toolchain on `PATH`; scoped Ruff and diff checks passed. The first broader invocation
had one preflight failure because `rustc` was not on that shell's `PATH`; no product
test failed, and the corrected exact suite passed. Startup time/RSS improvement is not
yet measured, and no package or native UI was opened.

## 11 September two-pet package closure

| Path | Review result | Evidence |
| --- | --- | --- |
| `apps/desktop/scripts/release-contract.mjs` | REVIEWED / EXTENDED | Immutable release constants bind the three retired hatch module names and their collected source-data paths. |
| `apps/desktop/scripts/build-sidecar.mjs` | REVIEWED / REPAIRED | PyInstaller excludes the retired modules from its archive and removes their exact collected `.py` data files before the runtime manifest is generated. |
| `apps/desktop/src-tauri/src/main.rs` | REVIEWED / REPAIRED | The convenience bridge-port wrapper used only by native tests is now compiled only under `cfg(test)`; release builds no longer warn about it. |

Exact source `9668bcc2afb5a080cfa0936d778c2f8c641544fa` produced both Windows
installers. The package verifier reported `release_ready:true` with zero blockers.
The runtime manifest has 2,372 files and zero retired hatch/image paths. Three
sequential packaged-bridge restart smokes passed with authenticated identity,
Zen/Muse free catalog defaults, cap 3, and zero provider calls. Complete desktop
contracts passed 290 with one intentional symlink skip; Rust passed 19/19 and a
warning-free release check. See
`docs/demo/evidence/PACKAGE_9668BCC_2026-09-11.md` for hashes and limitations.
