# Codex claimed correction dispatch — 5 September 2026

Goal ACTIVE; release NO-GO. Reviewed source **`fe34a3a12087aed23a3fd89a1806e0c122e2fc04`** was committed and pushed; exact remote main equality was verified. It extends accepted input-baseline source `6b7eeca`; it does not establish live Codex, Strands, AgentCore, visual UI, benchmark or submission readiness. The source commit contains 24 reviewed files; 19 Python paths passed Ruff and all 24 staged paths passed whitespace checks. The unowned supervisor loop remains excluded.

## Implemented behavior

- A separate append-only Store operation grants or revokes standing autonomous correction authority. The operator bearer identity is assigned at the authenticated API, not accepted from a request body or model output. Exact CAS binds current session control revision, goal/intent, project/workspace receipt and subscription incarnation. Pause, detach, reconnect, intent or workspace changes invalidate the grant; resuming does not regrant it. Existing observation-only receipts and generic adapter capabilities remain unchanged.
- The desktop connection panel exposes explicit enable/disable controls, the exact scope and canonical reload. Mutations run only from click handlers, reject stale responses and duplicate clicks, and are never automatically retried after uncertainty. Permission is not a worker-delivery receipt. The React review skill guided these request-lifetime and event-handler protections; browser/rendered verification of this new panel remains open.
- Pipeline tells the semantic supervisor about the separate permission through a bounded appended trusted note. It preserves existing safety-triage prefixes. A model cannot manufacture a grant by claiming one in its payload. The private capability exception is restricted to the four supported text actions and independently rechecked by Store.
- Pipeline carries the already-claimed event/effect ID, version, owner and frozen action into Executor. Executor requires the real shared adapter, exact accepted event baseline, persisted correction and current workspace. It revalidates Store authority rather than treating the claim reference as a reusable permission.
- Before the fresh control read, the adapter installs the exact attempted Store attribution. Complete accepted/current/fresh external-input digests must agree. It captures the current ledger revision after that installation, since installing provenance legitimately advances it.
- After transport lock waits, the synchronous final callback rechecks full Store dispatch authority using an independent connection/event loop, then current local policy, pause, adapter and workspace. Adapter and transport immediately recheck input/connection/parser/journal state. Verified idle selects one start; active selects one exact-turn steer. No generic send, consumer-drain wait, uncertain resend or steer-to-start fallback is introduced.
- Worker ACKs preserve the strict four-key delivery receipt. A pre-enqueue refusal after an existing dispatch claim is terminal `failed`, not an illegal dispatching-to-skipped transition. Post-enqueue uncertainty remains uncertainty, not confirmed failure or a retry opportunity.

## Independent review and development failures

Both bounded subagents use the user's requested GPT-5.6 Sol with medium reasoning. `sol_control_authority` owns Store/grant tests and independently reviews main integration/UI/context. `sol_shared_dispatch` owns the private adapter dispatch, its focused tests and local framed composition; it also reviewed Executor and migrated old Pipeline/workspace fixtures. Main reviews all owned production/test diffs and runs the combined gates.

Review repaired: missing JSON Content-Type on the UI mutation, valid goal revision zero incorrectly rejected, legitimate live goal-scope mismatch misclassified as database corruption, insufficient malformed-type guards, missing full-scope resampling before grant publication, and the capability exception requiring a real correction envelope. Main also caught an imported autouse fixture contaminating unrelated modules and a permission-note prefix that would have suppressed existing deterministic safety markers; fixtures are explicitly scoped and the note is appended instead.

The first 36-file combined run ended **935 passed, 1 failed, 8 setup errors in 268.14 seconds**. All nine failures were old echo/bootstrap fixtures attempting corrections with fabricated capability flags but without the new standing permission. Main replaced those flags with exact Store grants and refetched the post-CAS sessions before preparing effects. Existing assertions and production authorization checks were not weakened. Main affected echo/bootstrap/context gate: **17 passed in 19.95s**; independent overlapping gate: **62 passed**. Do not sum overlapping receipts.

Main desktop gate: **171 passed, zero skipped**, followed by successful `npm run build` (TypeScript and Vite). This is helper/source/build evidence, not new rendered/native UI proof. Combined Python and final framed-composition receipts are below.

The repaired 37-file backend run passed **947 tests in 278.33s**, with no skips. Main's two positive full framed-composition cases passed in **9.35s**: real local Pipeline, Store, grant, Executor, shared adapter, subscription, WebSocket framing and journal; fake supervisor decision/vendor I/O and workspace evidence collector. They verify one idle start or active steer, exact input/receipt, record-only echo, later observed agent response and no recursive correction. The fake later response is not independently proven useful work.

Full lost-ACK composition then exposed a separate lifecycle race: timeout invalidates the subscription; the observer cancels its consumer between Executor completion and the final receipt. The pump could finish with processing `planned` and main effect `dispatching`; startup recovery was required. Two independent deterministic tests also reproduced a lost acknowledged receipt by cancelling during post-Executor refresh or final sealing. Main now owns the entire refresh/reconciliation/seal as one retained task and joins it through repeated cancellation before propagating cancellation. Success, error and cancellation branches share this mechanism. Main's post-repair five-file cancellation/Pipeline/overlay gate passed **43 tests in 32.15s**; independent final cancellation/framed gate passed **6 tests in 16.24s**. Earlier 947-pass evidence predates this repair.

One exploratory cancellation teardown exceeded 60 seconds but later task-stack diagnostics did not reproduce that hang. Main's separate six-case rerun concurrently with the broad gate later showed five passes and one failure, then stalled in teardown; it was interrupted, without a completed failure traceback. Review identified another invalid timing assumption in the test: restart may find deferred followups already complete (`[]`) or revisit this one event (`[event_id]`). Only those outcomes are acceptable; the exact unchanged uncertainty receipt and a fresh count of one total worker write remain mandatory. This explains a test-oracle risk, not a proven cause of every observed teardown stall. No blanket deadlock repair or unsupported cause is claimed. The independent reviewer subsequently completed seven six-case runs without reproducing a stall; main's final frozen six-case gate passed **6 tests in 15.62s**, with no skips. Temporary diagnostic files were removed only after retaining the failure evidence here and the ordinary regression tests in the source commit.

## Main combined post-repair gate

**969 passed in 283.17 seconds, no skips, 41 complete files.** This main sweep includes the result-settlement production repair; the third focused cancellation case and final followup-list assertion adjustment are checked separately below. Overlapping runs must not be summed. Command: `.venv/Scripts/python.exe -m pytest -q`, all 31 paths listed in [`CODEX_INPUT_BASELINE_REVIEW.md`](CODEX_INPUT_BASELINE_REVIEW.md), these ten additional paths, then `--tb=short`:

```text
tests/unit/test_codex_autonomous_correction_grant.py
tests/unit/test_codex_autonomous_control_api.py
tests/unit/test_codex_claimed_executor.py
tests/unit/test_codex_claimed_executor_review.py
tests/unit/test_codex_shared_claimed_dispatch.py
tests/unit/test_codex_autonomous_supervisor_context.py
tests/unit/test_codex_main_settlement_cancellation.py
tests/unit/test_codex_correction_framed_pipeline.py
tests/unit/test_overlay_pipeline_recovery.py
tests/unit/test_overlay_executor_ledger.py
```

## Runtime refresh and remaining limits

Read-only checks at approximately 19:00 UTC / 20:00 WAT on 5 September found the currently resolved binary at `C:\Users\JosephMayo\AppData\Local\OpenAI\Codex\bin\2d468d2a6f48dd72\codex.exe`, SHA256 `BC15D59A3062BF165181A30007C3D0F5B1EE0CA4855E33D9B486AD59C984A31B`. This differs from the older audit artifact. The process scan found one Codex App Server, PID 14532, without an explicit shared-listener or remote-client flag; a bounded filename scan found no socket candidate. This is not exhaustive proof that no endpoint exists. No worker/proxy was launched or restarted.

The production ACL checker accepts that executable and its nearer directories but rejects `AppData` and `AppData\Local`. Read-only ACL inspection confirms an additional capability principal has full control there. No protection was weakened and no ACL was changed. A supported existing-worker endpoint and acceptable executable path remain required for the actual loop. Current [official App Server documentation](https://learn.chatgpt.com/docs/app-server) describes shared Unix/WebSocket connections and the remote CLI; it does not prove this installed binary/process is compatible.

The local SDK inventory includes Strands and Bedrock AgentCore; checked process environment variables do not configure a runtime ARN/provider/region. AWS authentication, deployed runtime state, Docker engine/ARM64 availability and paid invocation were not verified. Environment absence alone does not prove there are no saved credentials or deployed resources. The user identified their browser's AWS account for read-only checks, but has not specified region or spending cap. Browser auto-connect found no accessible debugging connection; no new profile or browser restart was used. No cloud resources, paid model calls or deployments were started. Do not infer that an unrelated local CLI profile belongs to the identified browser account.

The final synchronous Store helper uses one worker thread and SQLite's 5-second busy timeout. It has **no strict whole-call wall-time bound**, and can briefly block the application event loop. Filesystem/current-input checks are samples, not locks or server-side cross-client CAS. Client correlation is not vendor idempotency. Mocked vendor ACK/response examples are not independently verified useful human outcomes. Full received-stream/crash recovery and actual ten quiet tasks remain open.

The user reports the first bonus article published; no duplicate publication or bonus-award claim. Browser control remains paused after the physical Escape stop. Unowned `services/supervisor/src/pex_supervisor/loop.py` remains +28, SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`, excluded from staging. Tests use the dirty checkout, not a clean release.

## Next live milestone

The local checkpoint is reviewed and pushed. Resolve the live endpoint and AWS runtime prerequisites without replacing the user's worker or changing security settings silently. Prove actual existing-worker Strands NOOP, evidence-grounded correction and independently observed useful outcome, plus ten quiet tasks and actual AgentCore runtime. Continue every remaining three-spec/backend/UI/cross-harness/release requirement, exactly eight pets, and fair visible Cursor/Codex comparisons. The 6 September WAT target remains at risk; no local test count completes those gates.
