# PEX code audit coverage — 5 September 2026

Snapshot: 341 unique tracked or untracked source/configuration paths from the current checkout. Includes tests and fixtures. Excludes generated dependency lockfiles and node_modules/target/dist/results/_audit trees; release dependencies, raw evidence, assets and prose docs need separate targeted checks. This is an inventory, **not evidence that every file has been reviewed**.

All entries start `PENDING` for the fresh independent audit. Replace status only with specific coverage evidence from the reviewer; reading a diff, searching a symbol or passing a test does not equal full-file review. Record unresolved findings in SHIP_CHECKLIST.md or a linked findings log. New source files must be added and changed files re-reviewed.

## New-path addendum and bounded repair review

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
| `services/bridge/src/pex_bridge/supervisor_context.py` | FULL READ by main and supervisor owner; scope, redaction, validity and bounded selection; exact evidence observations remain separate |
| `tests/unit/test_opencode_outcome_lineage.py` | FULL READ by harness owner; main reviewed terminal and attribution cases; offline fixtures only |
| `tests/unit/test_supervisor_context.py` | FULL READ by supervisor owner; main reviewed integration and pagination boundaries; no real model execution |
| `tests/unit/test_worker_outcome_attribution.py` | FULL READ by main and independent integration reviewer; generic false-credit and foreign-authority regressions |

## Original snapshot

| File | Audit responsibility | Fresh audit status |
| --- | --- | --- |
| `apps/desktop/package.json` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
| `apps/desktop/scripts/build-sidecar.mjs` | UI / release | PENDING |
| `apps/desktop/scripts/record_submission_demo.py` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
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
| `apps/desktop/src/components/GoalEditor.tsx` | UI / release | FULL READ UI/release 5 Sep; findings open; later edits need re-review |
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
| `benchmarks/pex_attach.py` | Harness / integrity | PENDING |
| `benchmarks/pex_supervisor_process.py` | Harness / integrity | PENDING |
| `benchmarks/report.py` | Harness / integrity | PENDING |
| `benchmarks/runner.py` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_001_premature_stop/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_002_drift/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_003_permission_spam/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_004_false_claim/metadata.yaml` | Harness / integrity | PENDING |
| `benchmarks/tasks/pexbench_005_handoff/metadata.yaml` | Harness / integrity | PENDING |
| `deploy/agentcore/preflight.py` | Backend / release cross-review | PENDING |
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
| `integrations/opencode-plugin/pex-plugin.js` | Harness / integrity | PENDING |
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
| `services/bridge/src/pex_bridge/adapters/opencode.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/qwen.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/strict_json.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/synthetic.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/adapters/winfocus.py` | Harness / integrity | PENDING |
| `services/bridge/src/pex_bridge/agentcore.py` | Backend / release cross-review | PENDING |
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
| `tests/conftest.py` | Test cross-review | PENDING |
| `tests/contract/__init__.py` | Test cross-review | PENDING |
| `tests/contract/codex_live_proof.py` | Test cross-review | PENDING |
| `tests/contract/live_gate.py` | Test cross-review | PENDING |
| `tests/contract/test_authorization_inventory.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_capture_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_delivery_ack_hook.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_hooks.py` | Test cross-review | PENDING |
| `tests/contract/test_cursor_prompt_policy.py` | Test cross-review | PENDING |
| `tests/contract/test_intent_guardrails.py` | Test cross-review | PENDING |
| `tests/contract/test_live_agentcore.py` | Test cross-review | PENDING |
| `tests/contract/test_live_claude_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex_pump.py` | Test cross-review | PENDING |
| `tests/contract/test_live_codex.py` | Test cross-review | PENDING |
| `tests/contract/test_live_cursor_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_devin_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_grok_build_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_hermes_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_kimi_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_omp_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_opencode_stop.py` | Test cross-review | PENDING |
| `tests/contract/test_live_opencode.py` | Test cross-review | PENDING |
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
| `tests/unit/test_opencode_fork.py` | Test cross-review | PENDING |
| `tests/unit/test_opencode_pipeline_pump.py` | Test cross-review | PENDING |
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
