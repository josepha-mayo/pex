# Durable Codex correction provenance — 5 September 2026

Goal ACTIVE; product/release NO-GO. The user's 6 September WAT target remains at risk. Accepted source **`4f034e1a0dfe19a70c931f8269f44df339fdc55e`** was pushed with exact remote main equality verified. This is required infrastructure, not live Strands/AgentCore proof or control activation.

## Changes

- Pipeline calls `Store.prepare_main_effect_payload` before hashing/committing a main effect. The Store derives correction provenance from the durable accepted event and current published shared workspace, not model metadata. Commit freezes the supplied effect before awaits and recomputes its exact envelope transactionally; failure cannot partially commit an intervention/effect. Legacy envelopes remain unchanged.
- Correlation is deterministic from the stable main effect ID. It binds exact bounded UTF-8 text, effect/event/intervention, PEX session, vendor thread/root/project, physical workspace, origin and subscription. SEND_NUDGE, INJECT_CONTEXT and REQUEST_VERIFICATION require `send_message`; CONTINUE_SESSION requires `resume` and supplied nonempty text. No generic continuation phrase is invented.
- A correction-only SQL unique index prevents duplicate correlation ownership. A scoped trigger makes effect identity/target/payload/hash immutable while permitting lifecycle updates. No historical backfill; generic planner reservations reject correction metadata.
- `list_codex_correction_attributions` returns immutable canonical JSON strings `{correction, effect_state, effect_version}` after checking plan/intervention/hash/dispatch marker and stable scope. Old goal/subscription/epoch can support attribution, never dispatch. Endpoint changes refuse historical attribution. Reserved/skipped rows are excluded; failed rows require a dispatch marker because failure can follow a write.
- Loader overflow refuses rather than truncates: 4,096 candidate records/8 MiB selected strings before decoding; unused result data excluded. One externally corrupted SQLite row can still incur temporary fetch allocation before rejection. This is not a hostile-database memory sandbox.
- Adapter active-turn bookkeeping now clears only the matching completed turn. Late older STOP observations remain visible without erasing the newer active turn. Neither a completion nor a None field is fresh idle authority.

## Main verification

**551 passed in 135.77 seconds**, no skips, across 19 complete files. Command: `.venv/Scripts/python.exe -m pytest -q` followed by:

```text
tests/unit/test_codex_correction_store.py
tests/unit/test_codex_correction_pipeline.py
tests/unit/test_codex_shared_adapter.py
tests/unit/test_codex_shared_status_pipeline.py
tests/unit/test_codex_control_snapshot.py
tests/unit/test_main_effect_live_revalidation.py
tests/unit/test_event_processing_store.py
tests/unit/test_event_processing_pipeline.py
tests/unit/test_generic_dispatch_authority.py
tests/unit/test_workspace_continuity_store_review.py
tests/unit/test_workspace_continuity_pipeline.py
tests/unit/test_workspace_continuity_executor.py
tests/unit/test_workspace_publication.py
tests/unit/test_workspace_main_dispatch.py
tests/unit/test_codex_shared_read_snapshot.py
tests/unit/test_codex_shared_transport.py
tests/unit/test_codex_shared_text_dispatch.py
tests/unit/test_codex_subscription.py
tests/unit/test_codex_shared_attach.py
```

All eight changed Python paths passed scoped Ruff and staged whitespace checks. Tests use real temporary Store/workspace/Pipeline with explicit fake supervisor/vendor boundaries. Positive Pipeline cases inspect the already-dispatching durable effect inside the fake adapter, check the unchanged four-key worker receipt, and ensure replay does not resend. Preparation/insertion failures prove zero executor calls. None proves live inference or shared text delivery.

`transport_review` owned Store/helper/45 Store regressions. `attachment_review` independently reviewed that slice, then owned nine Pipeline regressions and the narrow older fixture repair. Main reviewed changed production paths/tests, wired Pipeline, reproduced/repaired stale turn bookkeeping, verified and pushed. The reviewer independently approved the Pipeline and stale-turn changes. This is not blanket whole-file/product approval.

Failures and review findings:

- Two initial Windows overlong pytest parameter-ID setup errors were fixed with bounded fixture IDs.
- Independent review found endpoint identity missing from historical scope and generic planner metadata able to poison the loader. Both were repaired and independently checked with temporary Store probes.
- Main's three stale-turn regressions failed before the match-only fix. Main then passed 53 adapter/status/snapshot tests; independent reviewer passed the same 53 in 8.64s.
- Three older workspace-main-dispatch fixtures failed because they hand-built the pre-contract payload. Only construction changed to the Store preparation API; original dispatch-refusal assertions remain. Reviewer Pipeline/old fixture/event recovery gate passed 27 in 22.71s.

Do not add overlapping gate totals. The 551-test run is the main receipt. Preserve unowned `services/supervisor/src/pex_supervisor/loop.py` +28 lines, unchanged SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`; it was excluded from staging. Tests are dirty-checkout evidence, not a clean release build.

## Next, in order

1. Exact client ID **and content** echo classification in live observations and fresh history. A prefix or loaded ID alone does not establish authorship. Preserve mismatch/partial-input uncertainty.
2. Store-validated record-only echo ingestion before human normalization/supervision. STATUS alone does not skip Pipeline. Install historical bindings in owned pump bootstrap before normalizing initial records, not in an await between publication and registry binding.
3. Coherent accepted human baseline: initial reconciliation STOPs must not inherit a later post-resume history digest. Refuse until coherent; never await drainage of the consumer currently executing the action.
4. Carry claimed effect through Executor/shared adapter to fresh local policy, input/turn checks, Store final validator and final transport revisions, then one start/steer write. Install the newly claimed correction before enqueue. Preserve the four-key worker receipt; richer provenance is separate. No uncertain resend or steer-to-start fallback.
5. Actual existing-worker Strands NOOP/correction/independently observed outcome and ten quiet cases under applicable authority; verified AgentCore runtime remains required by the intended stack. Then all full-spec/UI/backend/cross-harness/release/eight-pet/visible fair-comparison gates.

No generic shared capability enabled, worker/provider invoked, package/deployment produced or final submission made. Bonus articles are separate side work; see `posts/PUBLICATION_CHECKLIST.md` for actual publication state.
