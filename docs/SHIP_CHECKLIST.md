# PEX shipping checklist — 5 September 2026

## Target and truth standard

User target: **ship tomorrow, 6 September 2026 (Africa/Lagos)**. This is earlier than the official contest deadline (14 September, 5 PM PDT). Do not use the later contest date to defer essential work.

## Updated working objective

Audit all current PEX code independently against the three binding specifications, repair missing or incorrect behavior, and deliver an evidence-backed submission-ready app by 6 September 2026 WAT. Prove that the backend is a real independent goal-aware supervisor and the UI/UX is easy and genuinely helpful; then re-review all eight pets and perform visible live Cursor, OpenCode, and Codex baseline/+PEX comparisons with honest evidence, counted overhead, and no hidden-data leakage. Re-review every repair, push verified checkpoints, and keep working until the release gates are genuinely met or a specific external blocker needs the user.

The app's existing goal remains active. Its available tools allow status changes but not editing an unfinished goal's objective; this document records the updated working objective without falsely completing/replacing that goal.

## Ordered steps

1. **Read and inventory:** reread all three specs and important docs; inventory all code/configuration; establish a fresh independent audit ledger.
2. **Audit and prioritize:** split backend, harness/integrity, and UI/release reviews; turn evidence-backed findings into ranked repair tasks.
3. **Repair the real loop:** fix supervisor reasoning/evidence, same-session control, persistence, context, policy, outcome tracking, and recovery; prove both specific intervention and quiet NOOP.
4. **Complete the product:** fix onboarding and every primary UI-to-backend workflow; verify accessibility, offline/reconnect behavior, setup, and release artifacts.
5. **Review pets:** inspect and validate all eight built-ins in the actual app after the core/user flows are sound.
6. **Visible live verification:** keep PEX open for the user, inspect eligible UI with Computer Use, and run fair Cursor/OpenCode/Codex baseline/+PEX comparisons only after integrity gates pass.
7. **Final independent release review:** verify tests, actual usefulness, raw evidence, build identity, demo/docs, and remaining defects; give a concrete GO/NO-GO and obtain explicit authority for final publication/submission.

The user requested a fresh audit of all current code, including our own changes, against all three specs; a prioritized repair/build list; useful, easy UI/UX and sound backend logic; then a final eight-pet visual review and live Cursor, OpenCode, and Codex comparisons with PEX visibly open. This supersedes the old handoff's six-cell-only development restriction. It does not authorize fake results, silently dropped requirements, unsafe actions, or final public submission.

**Status: NOT READY.** Passing local tests, a running window, or a sent message alone cannot complete a release item. Every checked item needs source/commit plus a test, runtime trace, screenshot, or artifact. Keep implemented, locally tested, live verified, and unverified separate. Do not promise literal perfection.

## Binding inputs and audit discipline

- [x] Main reread `PEX_CORE_SPEC.md` completely this turn.
- [x] Main reread `PEX_BUILD_SPEC.md` completely this turn.
- [x] Main reread `PEX_IMPLEMENTATION_RECOVERY_SPEC.md` completely this turn.
- [x] Current handoff, status, known failures, architecture decisions, and integration matrix inspected; historical claims are not fresh evidence.
- [x] Initial tracked/new code and configuration inventory created in `CODE_AUDIT_COVERAGE.md`: 341 paths including tests, integration JS, desktop scripts and release configuration. Every fresh-review status starts pending; excluded generated/raw/asset/document groups need separate targeted coverage.
- [ ] Independent backend/logic review: supervisor, bridge, protocol, evidence, policy, intent/context, persistence, outcome attribution.
- [ ] Independent harness/integrity review: discovery, transports, adapters, plugins/hooks, benchmark execution and evidence boundaries.
- [ ] Independent product/release review: desktop/Tauri, onboarding, API wiring, interaction states, accessibility, error/recovery UX, packaging/docs.
- [ ] Consolidate findings with severity, spec clause, file/line, reproduction, fix owner, and verification. No blanket “all audited” claim from search hits or selected files.
- [ ] Re-review every repair batch, run proportional gates, update durable status, commit and push reviewed changes; verify remote hash. Never stage unrelated changes.

Main coordinates integration and verifies cross-domain behavior. Bounded subagents independently audit the three domains above; they start read-only and receive non-overlapping implementation ownership after findings are reviewed.

When specs conflict, preserve the stricter product/integrity contract: Core/Recovery zero access to hidden evaluator/oracles overrides Build's older hidden-evaluator inspection example; pluggable supervisor providers override older cloud-only framing. An unsupported vendor feature must be exposed honestly, not fabricated or silently erased.

## P0 — Real supervisor and safety (before cosmetic work or scored benches)

- [ ] Attach/discover an existing real Codex session and receive its actual events without replacing the user's harness.
- [ ] Persistent goal/criteria/constraints survive reload; correct session/project binding; intentional human updates supersede old intent.
- [ ] Observe external files/diff/test/process/artifact evidence, with source refs and freshness; distinguish unsupported from contradicted claims.
- [ ] Real Strands main inference and independent verification execute through a configured supported provider; provenance and overhead recorded, no secrets exposed.
- [ ] Correct completion: inspect and remain silent. Measure unnecessary interruption over ten correctly completed tasks; no canned stop warnings.
- [ ] Premature completion: identify exact unmet criterion, gather legitimate evidence, send specific correction to the same worker, observe its response, and verify completion.
- [ ] Uncertain claim: gather evidence before nagging; do not invent criteria or restore an unverified deterministic message after model failure/NOOP.
- [ ] Exact failed-test claim and incomplete artifact/row-count examples produce accurate evidence-backed decisions.
- [ ] Relevant context discovered by one real worker transfers minimally to another with provenance and observed use, not a planted hint.
- [ ] Useful trajectory/dependency/stagnation supervision works without repeated-intervention storms.
- [ ] Safe approval policy and consequential human decisions work; unsafe commands, cloud failure, replay, wrong session/project, and pause cannot bypass local authority.
- [ ] At least one truthful reversible overlay/handoff path works; unsupported controls are clearly unavailable.
- [ ] Bridge/adapters reconnect and restart without duplicate effects; incomplete/uncertain delivery is not claimed accepted/helpful.
- [ ] Complete observation → model → decision → policy → actual action → observed result audit, with unknown outcomes retained as unknown.

Current checkpoint in progress: truthful Cursor hook preparation/flush/activity ledger. Latest 12-file compatibility gate: **205 passed, 1 failed in 153.95 seconds**. The remaining failure is `test_presentation_listener_cannot_delay_or_invalidate_event_receipt`: a presentation task remains pending after the test drain. Earlier broad diagnostic run was interrupted after failures/stalled progress and is not a passing gate. Diagnose the remaining failure, retain receipt/timeout invariants, re-review the actual diff, and checkpoint only after the affected gate passes. These current changes are not yet committed or pushed.

## Immediate repair queue from the fresh audits

These are source-review findings, not completed fixes or live proof. Owners below describe domains, not permission for overlapping edits. Main must validate each finding and assign bounded non-overlapping changes before implementation. The 341-path inventory remains incomplete; a bounded audit is not whole-repository approval.

| Order | Task and owner | Required completion evidence |
| --- | --- | --- |
| 0 | Main: finish the current Cursor delivery checkpoint and diagnose the remaining presentation-drain test failure. | Affected tests pass; immutable preparation/flush/noncausal activity boundaries retained; independent diff review; exact pushed hash. |
| 1 | Harness owner + main pipeline integration: remove generic false outcome credit. `pipeline.py::_event_matches_worker_delivery` currently accepts all non-Codex/non-Cursor harnesses. Preserve OpenCode message/parent lineage instead of dropping it in SSE normalization. | Unrelated human prompt, old turn, missing parent and concurrent prompt cannot set `helped=True`; exact vendor-bound continuation tested; absent causal proof stays unknown. |
| 2 | Supervisor owner + main integration: carry bounded durable context and decisions into `SupervisorRequest` and evidence tools. They are loaded by the pipeline but omitted from semantic inference. | Relevant sibling result/rejected approach available with provenance; secret/local-only and unrelated-project material excluded; context selection auditable; empty context remains quiet. |
| 3 | Supervisor owner + main persistence integration: record the exact bounded evidence each model observed. Current tools can reread changing files and retain only tool names/model-authored strings. | Timestamped request/event-bound receipts or a genuinely frozen packet; main and verifier evidence independently identifiable; mutation-between-calls test; durable audit reproduces the observations. |
| 4 | Main: prove the real Codex supervisor loop before comparative runs. | Correct completion leads to model-backed NOOP; incomplete completion leads to specific verified correction in the same real session and independently verified final state; actual Strands main/verifier calls and overhead recorded. Extend quiet-case coverage to ten tasks. |
| 5 | UI owner: remove false quiet/canonical state, surface independent endpoint failures, and build a usable first-run connection flow. | No `All quiet` before live state; stale goals/roster/settings labeled unavailable; provider/auth, real worker attachment, goal and autonomy understandable; safe setup/install/health verification tested from a clean profile. |
| 6 | UI/release owner: repair startup/setup/docs/demo and verify an actual package. Hidden-window sidecar startup can fail before showing recovery UI. Installer currently uses plain Python after `uv sync` and references a nonexistent Attach control; demo recorder can screenshot an unauthenticated offline UI and still succeed. | Visible recoverable bootstrap on port collision/spawn/identity/timeout failure; synced interpreter and real supported attachment flow; authenticated readiness/source checks before demo capture; current asset names; complete sidecars and exact build hashes; isolated package smoke after applicable authority. |
| 7 | Harness/benchmark owner: repair evidence integrity before enabling a benchmark. Current Codex raw capture drops most frames and synthesizes timestamps/completeness; human intervention count is hardcoded zero. | Original complete permitted vendor events and timestamps retained; coverage gaps explicit; human actions observed or unknown; enforced hidden-evaluator/runtime isolation; no status-flag bypass. |
| 8 | Main + independent reviewers: finish remaining inventory, including semantic non-STOP actions, handoff criterion matching, remote evidence filtering, annotation delivery labels and pet-window privilege/placement. | Exact full/partial review coverage, regression checks, explicit unresolved severity, no unsupported product claim. |
| 9 | Final visible phase: inspect all eight pets and run eligible PEX/Cursor UI checks, plus native-protocol Codex/OpenCode work. | Actual app/source identity, screenshots and runtime traces; user-visible PEX; fair comparisons and honest failures/unknowns. |

Benchmark contract distinction: the three binding specs define the primary frozen benchmark as **four Cursor/Codex arms**. The user's added OpenCode baseline/+PEX makes **six requested live comparison cells**, not permission to silently rewrite the frozen four-arm schema. Preserve the original contract and add a separately labeled diagnostic/development comparison or explicitly versioned extension. Do not describe diagnostic smoke as a scored result. Existing runtime-boundary blockers remain blockers.

## P1 — Human-facing product and release flow

- [ ] Fresh onboarding: choose supervisor provider/model/auth, safely configure credentials, connect an existing worker, attach goal, and understand current autonomy level.
- [ ] UI reads canonical backend state; no confident synthetic/deep/accepted/helpful labels without evidence.
- [ ] Compact pet/inspector shows goal, last meaningful progress, why PEX acted, evidence, and only real decisions needing the user.
- [ ] Open agent focuses the correct existing session without accidental duplication.
- [ ] Ask PEX answers from its own state without interrupting the worker.
- [ ] Decisions, pause/resume, undo, context, goals, health, and settings work end-to-end; retries and stale revisions show useful recovery guidance.
- [ ] Loading, empty, offline, reconnecting, credential failure, unsupported adapter, long text, and narrow-window states are usable.
- [ ] Keyboard navigation, focus, contrast, readable status text, and unobstructed desktop interactions verified.
- [ ] Desktop typecheck/build/tests, backend/unit/contracts, and affected end-to-end gates pass; actual app verified, not only a browser mock.
- [ ] Startup and clean-profile setup work with no developer paths, secrets, missing sidecars/assets, or unexplained debug spam.
- [ ] Release/package smoke in an isolated target, with exact artifact hashes and reproducible instructions; obtain any still-required packaging/install authority before effects.

## P2 — Final pet review (after core and UI readiness)

- [ ] Use the hatch-pet skill for this phase; exactly eight built-ins: pex, ledger, mesh, nudge, drift, quiet, ember, von.
- [ ] Visually review every built-in at actual desktop size and each meaningful state/animation; inspect cropping, transparency, pacing, distinct character, readability, and distraction.
- [ ] Validate atlas/metadata/import boundaries and packaged asset completeness. Custom imports remain separate from the eight built-ins.
- [ ] Verify always-on-top, drag/placement, click-through behavior when enabled, compact/expanded interactions, and pause/offline states in the actual app.

## P3 — Visible live product tests and six-cell comparisons

- [ ] Open the verified PEX build visibly for the user; identify exact running app/window and backend/source identity. Do not quietly substitute a replay or another bridge.
- [ ] Use Computer Use for eligible PEX/Cursor visual interactions and UX inspection. Follow its mandatory restrictions: no terminal, authentication/security, ChatGPT desktop, Codex CLI/extension UI automation; use documented harness APIs/CLI tools or user participation for those surfaces instead. Do not fake UI coverage.
- [ ] Confirm exact installed Cursor, OpenCode, and Codex versions, model/settings, available login/provider access, and bounded run budget at execution time. No unlimited quota/spend.
- [ ] Preserve existing sessions and contest goal; use appropriately isolated benchmark tasks and goals. Resolve any conflict with the standing no-second-Cursor restriction before launch.
- [ ] Pass enforced runtime hidden-data/evaluator isolation and network-policy gates before any scored run. A manifest flag, ordinary subprocess, or `python -I` is not a sandbox.
- [ ] Freeze an honest within-harness protocol: equivalent public prompts/repo/models/settings/tools/network/budgets; no treatment suffix, oracle facts, task-ID interventions, or selective rescue.
- [ ] Capture immutable raw events, source/model/config identity, actual model calls, delivery/result evidence, failures/aborts, worker + PEX cost/time, and all task-changing human actions.
- [ ] Run Cursor baseline / +PEX, OpenCode baseline / +PEX, and Codex baseline / +PEX with visible PEX. Treat small-N demos as demos; do not invent statistical impact.
- [ ] Verify objective outcomes independently, review harmful/useless interventions, and report all failures and unknown coverage. No claimed win from prepared messages or locally synthesized IDs.

## P4 — Release decision and submission artifacts

- [ ] Final independent re-review of code, UX, safety, pet experience, live evidence, and release diff; unresolved P0/P1 findings explicitly listed.
- [ ] Public repository/license/README/setup accurate, architecture diagram reflects deployed reality, demo video <=5 minutes shows live usefulness, submission text avoids unsupported claims.
- [ ] Artifact/source hashes match tested build; reproducibility and limitations clear; user can actually start and use it.
- [ ] Present evidence-backed GO/NO-GO with exact remaining gaps. Final publish/deploy/submission actions require explicit authority; “ship tomorrow” is not permission to fabricate readiness or silently submit.

Do the next safe, highest-impact item immediately. If a required external choice or authority blocks a milestone, ask once with exact state and a concrete next action; continue independent safe work where possible.
