# Codex accepted input baseline — 5 September 2026

Goal ACTIVE; release NO-GO. Source **`6b7eecacc559bea05b8248836a92203c773b58e1`** was pushed with exact remote main equality verified. The 6 September WAT target remains at risk. This is an accepted evidence prerequisite, not enabled shared control or a completed supervisor loop.

## Behavior and review

The private bounded `CodexInputBaseline` seeds only from the immutable selected pre-resume full history and advances in first-observed live-prefix order. Each emitted event receives its own immutable content-free snapshot; later reconciliation/current history cannot grant authority to an earlier STOP. Missing, pending, truncated, conflicting, unsupported or oversized evidence has no usable digest. Unknown item types and input identity reuse cannot erase uncertainty. Complete exact corrections are excluded through Store-backed provenance; unknown clients remain external. Replacement provenance is scope-checked, additive and explicitly invalidates caches/revision; it grants no permission by itself.

Adapter bootstrap initializes the ledger before normalization, including interrupted-prefix handling. Private per-event sidecars survive until acknowledgment/successful retention. Pipeline requires the actual event's frozen sidecar when a ledger exists, never the latest mutable snapshot. Store validates the exact optional seven-field schema, types, bounds and digest/completeness relationship in acceptance and retention. Legacy observations stay legacy; absence is not backfilled as complete. Coordinator refuses non-false explicit truncation/redaction flags and incomplete content status at top-level and thread history boundaries.

Main reviewed production changes and every new test file. `transport_review` authored the ledger and independent real-Pipeline integration tests; `attachment_review` authored Store validation/tests and independently reviewed the ledger/coordinator. Review repaired a cache defect after a positive failing call-count reproduction: repeated unchanged snapshots classified the same input fifteen times rather than once. Store pre-fix malformed metadata tests produced seven failures with two legacy positives; coordinator completeness tests produced 58 failures with eight positives before repair. These are development failures, not runtime incidents. The independent final 131-test and 42-test gates overlap the main gate and must not be summed.

## Main final gate

**878 passed in 185.13 seconds, no skips, 31 complete files.** Ten changed/new Python paths passed Ruff and staged whitespace checks. Command: `.venv/Scripts/python.exe -m pytest -q`, these files, then `--tb=short`:

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
tests/unit/test_codex_input_baseline.py
tests/unit/test_codex_input_baseline_store.py
tests/unit/test_codex_history_coverage.py
tests/unit/test_codex_input_baseline_pipeline_review.py
tests/unit/test_codex_input_baseline_review.py
```

Tests include real temporary Store/Pipeline/workspaces with explicitly fake vendor/model boundaries, not live Codex/Strands/AgentCore proof. Unowned `services/supervisor/src/pex_supervisor/loop.py` remains +28, SHA256 `392367D79E07448785D3573B4F4E093648EE8303E73BB31032C1923D648B2604`, unchanged and excluded. Evidence is dirty-checkout testing, not a clean release build or a whole-repository audit.

All three binding specs were reread. The official App Server page was checked for read/start/steer semantics; the previously generated local parameter schema was inspected for optional client correlation. This does not verify compatibility of the currently installed vendor runtime. Correlation is not vendor idempotency; local authority/input samples cannot eliminate another client's subsequent input or provide a server-side idle/input CAS.

## Next acceptance gate

Carry the exact already-claimed main effect into one private shared dispatch path. Install its Store attribution before the fresh classified history read; require complete equal accepted/live/fresh external-input digests and capture the current post-installation ledger revision. Revalidate full Store authority and current local policy, pause, adapter, workspace and input state inside the transport's final synchronous callback after lock waits. Select verified idle start or exact active-turn steer once; preserve no retry/fallback and delivered versus uncertain outcomes.

Add explicit standing, revocable autonomous-correction permission without rewriting the existing observation-only receipt. Then prove actual existing-worker Strands NOOP, justified correction and observed outcome, ten quiet cases, AgentCore runtime, full remaining spec/release/UI/backend/harness/eight-pet and fair visible comparison requirements. No new runtime/provider/cloud/package/benchmark/submission action was performed in this checkpoint.
