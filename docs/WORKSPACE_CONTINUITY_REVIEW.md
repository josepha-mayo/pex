# Workspace continuity repair — 5 September 2026

## State and purpose

**Goal ACTIVE; product/release NO-GO.** Reviewed source/API guide committed and pushed as **`c0db4536db3c3cbb7366032e9bfdd9d22237aa4e`**, exact remote `main` equality verified. This is a bounded repair toward Core/Recovery's real existing-worker supervisor, not a replacement milestone or a whole-repository approval. User shipping target: 6 September WAT, still at risk. Starting attachment source: `f08ad8097775fa45b7057983b6365f5e9272623e`. The unowned 28-line supervisor `loop.py` edit is preserved and excluded from staging.

Main reread all three specifications and current handoff/operational sections. Binding requirements: actual workspace evidence, persistent human intent, correct existing session, no new effects from stale authority, truthful delivery/outcome history, low unnecessary interruption. Core/Recovery's zero hidden-evaluator access overrides Build's older contrary example.

## Reproductions and repairs

Main independently reproduced **15 failed / 4 passed** in the initial Store/Pipeline continuity tests. Attachment-time identity alone did not protect later processing: replacement directories could be inspected, stale model work could start, dispatch could proceed, and generic session updates could alter observer-owned metadata.

1. **Trusted Store witness.** Dedicated observer publication persists workspace, exact subscription, project binding and the server-selected origin configuration path transactionally. Later checks compare canonical and accepted session targets, selected locator ownership/JSON/membership, conflicting local directory claims, current origin and sampled physical directory. Client metadata and the database's parent directory cannot supply a missing trusted path.
2. **Immutable observer-owned metadata.** Generic discovery/upsert and event projections cannot mint, replace or drop workspace/subscription/coverage authority. Dedicated observer publication and canonical observer events remain the authorized paths. Existing fixtures that previously forged receipts via upsert now use that path; their rejection assertions remain intact.
3. **Evidence and planning.** Store fences acceptance, planner reservation/start, plan publication, main dispatch and reported-claim verification. Pipeline checks inside queued snapshot threads and scheduled supervisor calls as well as after results return. A cancelled owned snapshot thread is settled before the pump reports shutdown. Synchronous evidence tools use a separate Store read connection/loop; no Store transaction is held over model work.
4. **Revocable evidence tools.** The server installs an exact request-target callback, not a metadata-derived capability. Local reads check before/after and omit stale content from return values and the evidence collector. Scope copies in surviving threads share revocation. Remote AgentCore requests remain sanitized with no cwd or local metadata and use prefetched evidence, not remote local-path reopening.
5. **Truthful effect settlement.** Before-call rejection and actual delivery are distinct. A planner already marked dispatching but never entered becomes `failed` with `provider_started=false`, not an invalid `skipped` transition. Main queued dispatch refusal similarly becomes terminal failure; an already-called model retains its result before stale downstream use is rejected. Known worker delivery remains in the ledger after workspace loss, without projecting fresh session state. Overlay rollback and owned cleanup retain their separate recovery authority.
6. **Executor and direct handoff.** New sends, continuation, permission responses, lifecycle operations and overlay application recheck at the scheduled adapter-entry boundary. Context handoff checks both source and target. The operator's direct handoff path now uses the same check, with terminal failure and `adapter_started=false` on proven pre-call rejection. Terminal replay cannot redeliver.
7. **Ask PEX.** Completion checks use authority sessions rather than only display-filtered sessions, while excluding detached history in line with Store's completion projection. Answer threads check when actually entered. An independent review of the real answer function found that swallowed inspection failure could start a fallback after timeout/revocation; this was reproduced as **2 failed / 1 passed**. A separate revocable review scope now checks each outer provider branch, the scheduled Strands invocation and every HTTP fallback attempt. Valid fallback and current progress with detached history remain covered.

## Failed development cases retained

- The first queued-planner fix attempted `skipped` after a dispatch marker; Store correctly refused that transition, stranding the test. The fix uses terminal `failed` plus explicit proof the provider did not start. Store's state machine was not weakened.
- An Ask timeout test originally expired during the newly required entry check, before its held-answer barrier. Its test-only timeout became one second; production timeout was unchanged. Cancellation and surviving-thread assertions remain.
- Four legacy overlay Store stubs lacked the new guard method. Those explicitly unbound stubs gained an async `None` result; production did not gain a permissive missing-method fallback.
- The first operator-handoff fixture omitted required test Settings authentication; the fixture was corrected, not production behavior.
- Real-answer fallback and detached-history findings were discovered after an initially green bounded Ask suite. They are retained separately to show why mocked outer-call tests were insufficient.

## Verification ledger

- Previous attachment checkpoint: 545 passed / 2 skipped across 26 files. This applies only to its source hash.
- Initial continuity compatibility run: **967 passed / 3 skipped in 455.51 seconds**, 51 files. Excludes new Ask/operator-handoff files and later real-answer fixes.
- Focused Ask/provider gate after the review-scope fix: **53 passed in 45.98 seconds**, five files. Its collection preceded the final detached-history additions.
- Independent real-answer/detached-history file: **5 passed in 25.58 seconds**; scoped Ruff clean.
- Final main integration: **1,016 passed / 3 skipped in 627.20 seconds across 56 complete files**. All 27 changed/new Python paths passed scoped Ruff; all 28 staged source/test/API-guide paths passed whitespace checks. Source/API-guide push is `c0db4536db3c3cbb7366032e9bfdd9d22237aa4e`, verified against remote main.

The three skips are denied temporary symlink creation in `test_local_workspace.py:149`, `test_local_origin_config.py:221` and `test_workspace_inspect.py:130`; no permissions were changed. The gate ran in the user's existing checkout, with its excluded `loop.py` addition still present: a duplicate raise after an unconditional raise plus blank lines (SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`). This is not a clean-profile/package proof. The new failing subscription-close reproduction below is outside this accepted slice and this gate.

Reproduce the 56-file gate from the repository root with `.venv/Scripts/python.exe -m pytest` followed by these `tests/unit/` filenames and `-q -ra --tb=short`:

```text
test_codex_shared_transport.py test_codex_subscription.py test_codex_user_content.py
test_codex_shared_attach.py test_codex_shared_adapter.py test_observer_session_publication.py
test_observer_lifecycle_pipeline.py test_codex_attach_serialization.py test_codex_pipeline_pump.py
test_attach_security.py test_existing_sessions.py test_generic_dispatch_authority.py
test_event_processing_store.py test_event_processing_pipeline.py test_pipeline_session_merge.py
test_codex_shared_status_pipeline.py test_codex_partial_intent.py test_codex_observation_retention.py
test_observer_retention_store.py test_codex_reconciliation_retention.py test_local_workspace.py
test_local_origin_config.py test_local_origin_review.py test_workspace_attachment.py
test_workspace_attachment_review.py test_workspace_publication.py test_workspace_continuity_store_review.py
test_workspace_continuity_recovery_store.py test_workspace_continuity_pipeline.py test_workspace_access.py
test_workspace_continuity_tools.py test_workspace_continuity_executor.py test_workspace_main_dispatch.py
test_evidence_tools.py test_ask.py test_ask_review.py test_agentcore_runtime.py test_agentcore_pipeline.py
test_agentcore_client.py test_workspace_inspect.py test_store_mcp_verify_claim.py test_lifecycle_actions.py
test_overlay_executor_ledger.py test_cleanup_executor_ledger.py test_cleanup_restore_executor_ledger.py
test_overlay_pipeline_recovery.py test_overlay_runtime.py test_overlay_store_authority.py
test_context_handoff_protocol.py test_operator_handoff_effects.py test_supervisor_loop.py
test_workspace_continuity_ask.py test_workspace_operator_handoff.py test_workspace_ask_fallback.py
test_review_authority.py test_inspect_http.py
```

All these are local tests with temporary directories/SQLite and fake vendor/provider boundaries. Earlier overlapping gates must not be summed. No live worker, model, production origin configuration, GUI, normal package, benchmark, deploy or submission was run in this repair.

## Migration and limits

- A previously stored workspace binding without the new server-owned witness fails closed until explicit detach/reinspection. Do not guess its origin path or silently certify historical sessions. Truly unbound legacy paths retain prior behavior and are outside the new guarantee.
- Filesystem checks are samples, not an atomic directory lock, machine attestation, protection against inode reuse, or proof of the worker's retained cwd handle. SQLite/OS changes after the last sample remain possible.
- Checks at adapter/provider entry cannot retract already accepted work. Strands-internal model retries/turns within an already-entered invocation are not independently cancelled by the new review scope; local tool reads are revoked. Do not claim global cancellation or zero further provider processing.
- Project quarantine/reassignment has older artifact-authority settlement behavior outside this workspace-loss slice. Complete raw observation, process-crash recovery and owned coordinator-close settlement remain separate requirements.
- Shared Codex sending/steering/approval/configuration is still unavailable. An endpoint or receipt is not same-worker control proof. Current input/turn/connection-epoch authority and protected installed-runtime evidence remain required.

## Next critical path

The continuity slice and subsequent bounded close-ownership repair are accepted/pushed; the latter is documented below. Next implement the minimum connection workflow and actual existing-worker control, including required durable/raw recovery. Do not enable generic shared messaging merely because workspace checks pass. An operator-confirmed single action can be a diagnostic, but does not replace autonomous goal-aware supervision or prove reduced human babysitting.

OpenAI Docs was used to recheck [App Server turn semantics](https://learn.chatgpt.com/docs/app-server): steering checks the expected active turn; starting a turn is a distinct operation. No documented idle/input compare-and-swap was established. A local lock is not a server-side fence against another client; any cooperative interaction constraint must be explicit, not implied by subscription consent. Rejected steering must never fall back to a new turn.

Then prove real Strands NOOP and exact correction with observed same-worker outcome, ten quiet cases, remaining full-spec/human workflow, normal release, exactly eight pets, visible fair Cursor/Codex four-arm comparisons and separately labeled OpenCode diagnostics, followed by independent submission review. Winning remains the aim, never a fabricated rank or readiness claim.

## Subsequent accepted repair: owned subscription close

Source **`c15a2fce3ae9b5c9c1db2b530cd76eb4b29a5acc`** is pushed with exact remote equality verified. Changed paths: `codex_subscription.py`, existing `test_codex_subscription.py`, new `test_codex_subscription_close_ownership.py`. Main reviewed the changed method/callers and new test file; `transport_review` implemented it and `attachment_review` independently reviewed it plus actual transport cleanup. This is not approval of the entire coordinator/transport file or product.

The baseline fake-transport reproduction was **2 failed / 2 passed in 2.48s**: caller cancellation returned while shielded close remained alive. The fix creates exactly one close task and waits for settlement through repeated cancellation. It never retries close, retains the original failure, and grants no reuse authority. An existing interrupted-prefix test needed its held-close barrier released before awaiting the now-correctly pending caller; all prefix/revocation assertions remain, with new pending/closed assertions. The initial run against its old barrier hung and was interrupted, not counted green; only the exact test-owned pytest child was stopped. All fixture tasks are released and joined.

Final focused owner gate: **90 passed in 4.64s**; independent reviewer: **90 passed in 4.47s**. Main integration: **355 passed in 179.14s across 17 complete files**, no skips. Scoped Ruff and staged whitespace passed for all three paths. Counts overlap each other and the earlier continuity gate; do not sum them. Reproduce with `.venv/Scripts/python.exe -m pytest`, these `tests/unit/` filenames and `-q -ra --tb=short`:

```text
test_codex_shared_transport.py test_codex_subscription.py test_codex_subscription_close_ownership.py
test_codex_shared_attach.py test_codex_shared_adapter.py test_observer_session_publication.py
test_observer_lifecycle_pipeline.py test_codex_attach_serialization.py test_codex_pipeline_pump.py
test_existing_sessions.py test_generic_dispatch_authority.py test_codex_shared_status_pipeline.py
test_codex_partial_intent.py test_codex_observation_retention.py test_observer_retention_store.py
test_codex_reconciliation_retention.py test_workspace_continuity_pipeline.py
```

Tests cover single and three separately delivered caller cancellations, ordinary settlement, close failure, direct cancellation of the owned close and frozen interrupted-prefix retention. Actual shared transport revokes connection authority before awaited cleanup and bounds channel close; the coordinator does not create a second close. **Task settlement is not successful transport termination:** a failing or directly cancelled close remains an unsuccessful close. An arbitrary noncooperative injected transport could remain pending. No general crash-durability or shared-control proof follows. Tests used temporary state/fake vendors and the unchanged excluded `loop.py` worktree described above; no live worker/provider/GUI/release/submission ran.
