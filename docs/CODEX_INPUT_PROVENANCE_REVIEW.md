# Codex input provenance and echo ingestion — 5 September 2026

Goal ACTIVE; product/release NO-GO. The user's 6 September WAT target remains at risk. Source **`9ba5f394b14040e8e0808f7101f1dc821084d5b3`** was pushed with exact remote main equality verified. This bounded checkpoint separates attempted PEX corrections from actual external input; it does not activate shared control or prove the real Strands/AgentCore loop.

## Implemented behavior

- Immutable `CodexInputProvenance` indexes only canonical records supplied by Store's validated attribution loader. The classifier itself does not authenticate arbitrary JSON. Exact client correlation **and complete identical content** are required; unknown prefixes remain external, known mismatches/partial content remain uncertain. UTF-8 text-element boundaries, explicit content shape, bounded bytes/counts and duplicate identities are checked. Ordered history snapshots exclude only exact owned corrections; uncertain or repeated correction identities make the external-input digest unavailable.
- Production attachment supplies the real Store loader to the pump's owned receiver bootstrap before initial live records are normalized. It introduces no await between publication and adapter binding. Bootstrap failure/cancellation joins owned work; interrupted records cannot be normalized as human input before the required provenance dependency succeeds. Direct and wrapped pump entry points enforce the same requirement.
- Exact completed live echoes become STATUS with identity/digest metadata and a private raw-item sidecar. Pipeline witnesses the actual queued adapter object, then Store independently validates the attempted immutable effect, current workspace/attachment and exact raw input before a record-only transaction. No human override, model call, new action, goal/session projection or delivery-state advancement occurs. Generic ingestion rejects correction/observer markers.
- All incomplete `item/started` user inputs are recorded without supervision or an authorship claim. A completed external message still enters ordinary supervision; an incomplete/conflicting one cannot establish human-override authority. Live pending recording requires current workspace samples before commit. Stopped-pump retention intentionally preserves old received evidence after workspace revocation without projecting it; its contract remains separate.
- One correlation appearing on different live vendor inputs becomes uncertainty rather than a second exact echo. Store enforces multiplicity inside the same write transaction, including disconnect retention; competing writers can commit only one distinct input. Same-input/event replay preserves original goal/time/publication. A new attachment without the first vendor tuple may discover the conflict only at Store: a typed permanent error closes the pump rather than retrying indefinitely. Failed prefix retention is disclosed; no claim that this case transparently recovers.
- Sidecars live as long as their undelivered observations and are removed only after acknowledgment or successful retention. Failed retention leaves the owned evidence and reports the gap. No raw message is copied into correction event metadata.

## Review and development failures

Main integrated the adapter, attachment, Pipeline and Store. `transport_review` authored the classifier/tests and independent bootstrap/recovery regressions; `attachment_review` authored real temporary Store and receiver/Pipeline tests and independently reviewed the integration. Both independently approved the final bounded slice. Main reviewed all changed production paths and new test files. This is not whole-file or whole-repository approval.

Reproduced and repaired before acceptance:

1. Workspace replacement during an awaited Store lookup could pass an earlier sample; the exact-echo path now resamples immediately before either commit/replay return.
2. Direct pump startup omitted the bootstrap-required flag: one failing real interrupted-prefix regression, then both entry paths passed.
3. Two distinct vendor items sharing one genuine correlation were both suppressed as exact: one failing receiver/Pipeline regression, then uncertainty and transactional competing-writer tests passed.
4. Known partial `item/started` invoked the supervisor before exact completion: one failing real Pipeline regression, then no-start-inference and ordinary completed-external positive controls passed.
5. The first workspace-check integration accidentally blocked stopped evidence retention: main reproduced four continuity failures. Checks were narrowed to the explicit live-pending mode; independent 65-test gate, including continuity and retention, passed afterward. Assertions were not weakened.

The cross-attachment permanent-error regression was first executed after the typed-error fix; it is post-fix evidence, not a claimed pre-fix runtime reproduction. Intermediate overlapping gates (138 focused, 663 broader before final pending-input refinements, and reviewer 65) must not be summed or substituted for the final main receipt.

## Main final verification

**703 passed in 165.28 seconds**, no skips, across 26 complete files. All ten changed Python paths passed scoped Ruff and staged whitespace checks. The command was `.venv/Scripts/python.exe -m pytest -q` followed by:

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
tests/unit/test_codex_correction_observation_store.py
tests/unit/test_codex_input_provenance.py
tests/unit/test_codex_provenance_bootstrap.py
tests/unit/test_codex_correction_echo_pipeline.py
tests/unit/test_codex_reconciliation_retention.py
tests/unit/test_codex_observation_retention.py
tests/unit/test_observer_retention_store.py
```

Tests use temporary real Store/workspace/Pipeline and explicitly fake vendor/supervisor boundaries, not installed Codex delivery or model inference. Preserve unowned `services/supervisor/src/pex_supervisor/loop.py` +28 lines, SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`; do not stage or clean it. Tests remain dirty-checkout evidence, not a clean release build.

## Exact next work

1. Freeze a coherent accepted external-input baseline per observation, seeded only from the earlier selected history, advanced in live-prefix order. Never attach later post-resume history to an earlier STOP. Missing/unsupported history is incomplete, not empty. Raw content stays private; accepted metadata carries completeness/digest/revision only.
2. Carry the claimed main effect through Executor/shared adapter. Compare fresh classified input history with that trigger's persisted baseline, recheck live policy and exact Store authority, then final transport revisions and one start/steer enqueue. Register the newly attempted correction before enqueue; never await the consumer's own drainage/echo. Preserve four-key worker receipts and no uncertain resend/steer fallback.
3. Prove actual existing-worker Strands NOOP, grounded correction, independently observed outcome and ten quiet cases, with verified AgentCore runtime for the intended stack. Then finish all remaining full-spec UI/backend/cross-harness/release/eight-pet/fair visible comparison gates.

No worker/provider/native UI/deployment/package/benchmark/submission was run by this checkpoint. The first short bonus article remains saved/previewed in the user's existing Brave, awaiting Publish confirmation, not public. See `posts/PUBLICATION_CHECKLIST.md`; posting stays secondary to the real loop.
