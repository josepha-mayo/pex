# PEX shipping checklist — 5 September 2026

## Target and truth standard

Latest reviewed source push: `67168204b11331a4a3db21b20e09a6900f3bbec5`, exact remote `main` equality verified. Source gates below apply to that checkpoint, not to the preserved unowned `loop.py` edits.

User target: **ship tomorrow, 6 September 2026 (Africa/Lagos)**. This is earlier than the official contest deadline (14 September, 5 PM PDT). Do not use the later contest date to defer essential work.

Current reviewed provider/setup source: **147 backend/setup tests passed, 1 symlink-environment skip; 97 desktop checks and TypeScript passed.** Credential destinations/revisions/races and safe source setup now have bounded regressions; see the current handoff for the exact scope and security incident. Existing-session Codex control, rendered UI and release readiness remain open. Earlier pushed evidence/startup source: `1574c56d00a41a0f9d1769e3c1b6a85e59e0af72` (332 backend, 74 frontend, 12 Rust tests under a disclosed sidecar override). Preserve the still-changing unowned `loop.py` diff; no clean-tree or live-product claim.

## Updated working objective

Maximize PEX's chance of winning the hackathon by delivering a useful, spec-compliant, evidence-backed submission-ready app, targeting 6 September 2026 WAT. Independently audit all current code against the three binding specifications and repair missing or incorrect behavior. Prove a real independent goal-aware supervisor over the user's existing worker, with easy and genuinely helpful UI/UX; then re-review all eight pets and perform visible live Cursor, OpenCode, and Codex baseline/+PEX comparisons with honest evidence, counted overhead, and no hidden-data leakage. Re-review every repair, push verified checkpoints, and keep working until the release gates are genuinely met or a specific external blocker needs the user. Winning is the aim, not a result we can guarantee.

The app's existing goal remains active. Its available tools allow status changes but not editing an unfinished goal's objective; this document records the updated working objective without falsely completing/replacing that goal.

## Immediate execution plan — latest goal/TODO request, 5 September

**Latest repair progress:** the durable Store boundary now snapshots session/control/project/target authority and rejects changed goal intent or later accepted human input. Cwd ABA and stale-plan target rollback are repaired. Fourteen new regressions and independent review cover this source slice; the latest handoff records final integration/push status. Step 2 is not universally complete: global-pause ABA, raw input, actual transport epochs and post-claim races remain open. Shared transport/coordinator are separate uncommitted WIP awaiting integration review; do not count them as live existing-worker support.

**Goal state: ACTIVE. Release state: NO-GO.** This section refines the next actions; it does not mark new implementation complete. Target remains 6 September WAT. Required quality means demonstrated spec compliance and usefulness, not a promise of literal perfection or a guaranteed win.

1. **Reconfirm the contract and source boundary (main).** Read all three binding specs, current handoff and important status files before each repair cycle. Preserve the unexplained `loop.py` edit. Track every code/configuration path in `CODE_AUDIT_COVERAGE.md`; selected reviews are not a whole-repository audit.
2. **Close stale-action authority before enabling shared mutations (main implementation; credential reviewer independent review).** Reproduce the reviewer's temporary-Store findings: an older action was granted after a same-goal objective change, pause/resume, and a later accepted human prompt. Atomically compare the accepted intent revision/hash, session control revision and human-input watermark at the actual dispatch boundary. Exit: each stale case is denied before adapter effects, valid current actions still work, and replay/concurrency tests plus independent diff review pass. These findings are reviewer-reproduced, not yet main-verified or fixed.
3. **Build and integrate the actual existing-worker connection (transport and subscription owners; main integration).** Implement the proposed shared endpoint transport and exact selected-thread subscription separately. Bind endpoint, connection generation, thread, project/cwd and explicit selection authority; reconcile history and live events without invented timestamps, completion or coverage. Reject malformed identity, gaps and stale generations. Main then implements authenticated recoverable attachment and truthful per-session state. Exit: bounded fake-transport tests and cross-review first, followed by separately authorized installed-runtime proof. A read-only connection is an intermediate slice, not the finished supervisor.
4. **Separate active steering from idle continuation (main; credential reviewer).** Validate the installed protocol before live use. Active nudges must target the exact active turn; rejection must not fall back to starting a turn. Idle continuation needs its own authority and concurrency policy. Preserve the user's existing cwd, approval and sandbox configuration unless a separate explicit overlay authorizes a change. Capture documented human-message content and immediate turn/input watermarks before asynchronous reasoning. Exit: stale/wrong-turn, newer-human-input, autonomy-level and configuration-preservation regressions pass; actual same-worker delivery/outcome proof remains separately required.
5. **Prove the real supervisor, then finish the human workflow (main + independent evidence reviewer).** Complete actual Strands main/verifier NOOP and specific-correction cases, then ten quiet cases, with real observations, same-worker outcomes and measured overhead. Verify provider setup → existing worker → persistent goal → supervision → pause/decision/undo/reconnect in the rendered app. Close all remaining release-blocking source audit findings. Do not substitute mocks or helper tests for these receipts.
6. **Finish release, all eight pets, visible comparisons and final review.** Verify normal build/sidecars and clean-profile startup; inspect all eight pets in the actual app after primary flows work. With PEX visible and the applicable UI skills, run the four formal Cursor/Codex baseline/+PEX arms and separately labeled OpenCode pair only after fairness/isolation gates. Record failures and uncertainty, prepare accurate demo/setup artifacts, and make an evidence-backed GO/NO-GO. Final publication/submission still requires explicit authority.

### Bounded agent ownership for the next repair cycle

| Owner | Bounded responsibility | Current evidence/state |
| --- | --- | --- |
| Main | Authority repair, existing adapter/API integration, UI-to-backend integration and final verification | Planned; no new completion claim in this planning update |
| `codex_audit` | New `codex_shared.py` transport and `test_codex_shared_transport.py` | Assigned; implementation/review receipt pending |
| `opencode_audit` | New `codex_subscription.py` coordinator and `test_codex_subscription.py` | Coordinator source exists as unlinted, untested WIP; tests and independent review pending |
| `credential_review` | Independent delivery/authority review and reproduction; no overlapping source edits | Reported three stale-authority reproductions and human-prompt normalization gap; main verification pending |

**Working checklist for every step:** [ ] reproduce/read evidence → [ ] implement with focused regressions → [ ] independently review the diff → [ ] run integration checks → [ ] update coverage/handoff and remaining blockers → [ ] commit only reviewed paths and push → [ ] verify remote hash. Do not mark a step complete from an agent report alone. Keep live/provider, process disruption, package/freeze and publication gates explicit; continue safe independent work while a gated action awaits authority.

**Delivery race to retain in the design:** an expected active-turn ID does not fence newer human input inside that same turn. Local accepted-input checks alone also cannot exclude input not yet observed. Verify observation coverage and disclose any remaining race; strict exclusion may require a cooperating input arbiter/window, especially for idle launch. Unknown coverage must not be promoted to proof of current authority.

## Next-cycle TODOs — execute in this order

These are actionable next steps, not completed work. Main owns integration and the final evidence checks; bounded subagents review non-overlapping domains. Preserve unrelated local edits throughout.

- [x] **Finish the current credential-settings source repair (main).** Destination binding now includes visible named-provider endpoints; callbacks, stale-response guards, explicit revision authority and bounded uncertain-write recovery are wired. Independent review drove an additional backend catalog credential-race repair. Local regression and TypeScript gates passed; the current handoff records exact evidence. Rendered UI/provider proof remains a separate unchecked gate.
- [ ] **Resolve existing-worker attachment truth (Codex reviewer, main integration).** The independent source review reports that attachment launches a separate PEX-owned app-server child and reads only that child's notifications; listing/resuming stored thread IDs does not prove observation or control of the original user's active worker. Main must verify these findings, establish a supported same-session event/control path, and implement and test the smallest spec-correct connection flow. Also check failed-attach recovery and the missing desktop attach action. Do not label an isolated session as proof of existing-worker control.
- [x] **Repair first-run source instructions and bootstrap (setup reviewer, main integration).** Correct uv/npm sequence, fail-fast native commands, no default global hook mutation, all-sidecar requirements and real worker/session/goal instructions are implemented and reviewed. Isolated fake-command PowerShell tests verify execution order and cwd restoration. No actual install or packaged/clean-profile proof is claimed.
- [x] **Integrate and push the bounded provider/setup repair checkpoint (main).** Reviewed changed lines, ran combined gates, updated audit coverage/handoff, staged only reviewed files and verified remote equality for `67168204b11331a4a3db21b20e09a6900f3bbec5`. The unexplained `loop.py` edit remains outside the checkpoint. Repeat this discipline for each subsequent batch.
- [ ] **Prove the core live loop (main, independent evidence reviewer).** Check source identity, provider access and applicable run authority first. Capture one correctly completed task yielding real model-backed NOOP and one incomplete task yielding a specific verified correction to the same worker, followed by independently verified completion. Then run ten quiet cases. Record actual main/verifier calls, costs, failures and outcomes; no synthetic substitute.
- [ ] **Close primary user-flow and remaining audit gaps (domain owners).** Verify provider → existing worker → persistent goal → supervision → decision/pause/undo/reconnect, including failure and accessibility states. Finish the path-by-path audit and fix remaining release-blocking findings. Do not expand optional features while core gates remain open.
- [ ] **Finish the release candidate and final visual phase (main + reviewers).** Validate all required sidecars and normal release configuration, then clean-profile startup and all eight pets in the actual app. Retain exact build/artifact identity. Follow applicable authority gates before packaging or launching disruptive processes.
- [ ] **Run fair visible comparisons and final release review (main + independent reviewer).** First close raw-event, human-action accounting and runtime/evaluator isolation gaps. Run the four formal Cursor/Codex arms and separately labeled OpenCode diagnostic pair, with PEX visible. Prepare accurate setup/demo/submission artifacts and an evidence-backed GO/NO-GO; obtain explicit final publication/submission authority.

**Completion rule:** a checkbox is complete only when its stated exit condition has a linked receipt (review, tests, runtime evidence or artifact as appropriate). A local test does not satisfy a live UI, same-session, provider or release requirement. Keep blocked items visible with the precise missing prerequisite; continue safe independent work without silently lowering the bar.

## Ordered steps

1. **Read and inventory:** reread all three specs and important docs; inventory all code/configuration; establish a fresh independent audit ledger.
2. **Audit and prioritize:** split backend, harness/integrity, and UI/release reviews; turn evidence-backed findings into ranked repair tasks.
3. **Repair the real loop:** fix supervisor reasoning/evidence, same-session control, persistence, context, policy, outcome tracking, and recovery; prove both specific intervention and quiet NOOP.
4. **Complete the product:** fix onboarding and every primary UI-to-backend workflow; verify accessibility, offline/reconnect behavior, setup, and release artifacts.
5. **Review pets:** inspect and validate all eight built-ins in the actual app after the core/user flows are sound.
6. **Visible live verification:** keep PEX open for the user, inspect eligible UI with Computer Use, and run fair Cursor/OpenCode/Codex baseline/+PEX comparisons only after integrity gates pass.
7. **Final independent release review:** verify tests, actual usefulness, raw evidence, build identity, demo/docs, and remaining defects; give a concrete GO/NO-GO and obtain explicit authority for final publication/submission.

## Execution board and deadline order

The objective is maximizing the chance of winning by shipping a useful, credible product, not maximizing test counts or claiming perfection. Work down this board; audit and repair can overlap across bounded owners, but live comparisons cannot bypass the real-product and integrity gates.

| Stage | Current state | Next concrete action / exit condition |
| --- | --- | --- |
| Spec-first audit | IN PROGRESS | Finish the path-by-path coverage ledger. Three independent domain reviews have findings; 49 initial paths have recorded full reads, not whole-repository approval. Re-review repaired paths. |
| Critical backend repairs | IN PROGRESS | Exact separately bound main/verifier observations and timeout/crash preservation now pass local regressions, alongside prior outcome/context repairs. Next: prove the real same-session supervisor loop and ten quiet cases. |
| Human-facing product | IN PROGRESS | Canonical state and visible serialized startup recovery have source/unit checks. Next: usable first-run connection and actual primary-flow UI-to-backend verification. Missing frozen cursor-observe binary still blocks normal release-build proof. |
| Eight-pet review | NOT STARTED in this fresh audit | After core and primary flows work, inspect all eight pets at actual desktop size and in meaningful states; validate packaged assets. |
| Visible harness comparisons | NOT STARTED | Verify running source identity, approved access/budget, and enforced evidence isolation. Run the four spec-defined Cursor/Codex arms plus the separately labeled OpenCode diagnostic pair; report all failures and unknowns. |
| Release decision | NO-GO | Complete clean-profile/package checks, accurate demo/setup/submission artifacts, final independent review, and explicit final publication/submission authorization. |

**Deadline discipline:** 6 September WAT is the internal ship target. Prioritize one genuinely working supervised human workflow, then remaining required coverage; defer optional expansion and cosmetic redesign. Do not defer safety, real model evidence, same-session control, recoverable setup, or honest reporting. If the target is at risk, report the exact remaining gates and tradeoffs instead of silently moving the date or checking unverified items.

**Every repair cycle:** reread the applicable spec sections and current handoff → reproduce the finding → assign non-overlapping implementation ownership → implement with regressions → independent diff review → integration checks → update this board/handoff → commit and push only verified scoped changes → verify the remote hash. A subagent's green report alone is not the integration gate.

Earlier verified source push: **`a779404082edb3fe861a643bf1f981eeb5373b40`** (outcome/context/UI repair and updated execution board). The working tree was clean immediately after that historical push, not necessarily now. Local gates then: 298 backend tests; separate overlapping 191-test compatibility run; 67 frontend checks and TypeScript. The newer source checkpoint is listed at the top of this document. Full scopes and limitations are in the handoff; no live/product/release claim follows from these counts.

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

Pushed checkpoint: truthful Cursor hook preparation/flush/activity ledger, **`c519883190c57566e6b5823042193b0e20936146`**, with exact local/remote equality verified. The test helper now drains descendant presentation tasks; production timeouts and strict listener-independence assertions are unchanged. Stable 12-file gate: **206 passed in 134.00 seconds**; separate Codex pump/fleet gate: **77 passed in 79.92 seconds**; adapter-capability file: **24 passed in 14.05 seconds**. Total **307 across 15 distinct files**, scoped Ruff clean; bounded independent review's stale-test finding corrected. The earlier 205/1 run and interrupted broad diagnostic run are retained in the handoff as failures, not green evidence. This is not live product proof and does not cover later edits.

## Immediate repair queue from the fresh audits

These are source-review findings; status prefixes distinguish completed source slices from remaining work. None is live proof unless explicitly recorded. Owners below describe domains, not permission for overlapping edits. Main must validate each finding and assign bounded non-overlapping changes before implementation. The initial 341-path inventory plus new-path addendum remains incompletely reviewed; a bounded audit is not whole-repository approval.

| Order | Task and owner | Required completion evidence |
| --- | --- | --- |
| 0 | PUSHED SOURCE: Cursor preparation/flush/activity checkpoint; presentation-drain regression fixed. | Commit `c519883190c57566e6b5823042193b0e20936146`, 307 scoped tests, independent review. Live vendor acceptance and useful continuation remain unproven. |
| 1 | PUSHED SOURCE: generic outcomes fail closed and OpenCode retains exact assistant parent lineage. | Commit `a779404082edb3fe861a643bf1f981eeb5373b40`: unrelated human prompt, old turn, missing parent, uncertain delivery and scope mismatch regressions; exact parent-bound terminal result; unsupported causal proof stays unknown. Live run remains open. |
| 2 | PUSHED SOURCE: bounded durable context/decisions reach the frozen supervisor request and paged evidence tools. | Same checkpoint: sibling evidence/rejected approach available with provenance; private/foreign/stale material excluded; offered IDs and packet hash retained; replay uses original packet. Offered does not mean model-used; exact tool observations remain task 3. |
| 3 | VERIFIED LOCAL SOURCE: exact bounded observations and citations separately identify main and verifier evidence. | Final 332-test backend gate includes changed-file-between-calls, strict request/ref/hash binding, serialized concurrent budget, failure/timeout/crash preservation and NOOP replay. Actual model use/understanding and live effectiveness remain unproven. |
| 4 | Main: prove the real Codex supervisor loop before comparative runs. | Correct completion leads to model-backed NOOP; incomplete completion leads to specific verified correction in the same real session and independently verified final state; actual Strands main/verifier calls and overhead recorded. Extend quiet-case coverage to ten tasks. |
| 5 | PARTIAL SOURCE REPAIR: false quiet/canonical state and independent endpoint failures addressed with local tests. First-run connection flow remains OPEN. | No `All quiet` before live state; cached/failure states labeled; stale-revision actions blocked. Still require visible UI validation and understandable provider/auth, real worker attachment, goal and autonomy from a clean profile. |
| 6 | PARTIAL LOCAL SOURCE: startup recovery plus provider/source-bootstrap repairs are reviewed. Wrong Python/default global hooks/nonexistent Attach instructions are corrected; actual onboarding/demo/package remain open. | Latest bounded setup/provider gate: 147 passed/1 skip; 97 frontend checks/TypeScript. Earlier 12 Rust tests needed a test-only externalBin override because frozen cursor-observe is missing. Still require normal release config, packaged bootstrap/port/crash/retry smoke, real attachment flow, authenticated source-valid demo and exact package hashes. |
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
