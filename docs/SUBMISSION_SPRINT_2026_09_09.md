# PEX submission sprint — target 9 September 2026, WAT

The full goal remains active. This is the user's three-day internal target, not
a claim about the organizer's current deadline. Submission status: **NO-GO**.
Read all three binding specs and `CHECKPOINT_2026_09_06.md` before each work cycle.
Conserve quota: no new subagents or live-model runs in the current work cycle.
If independent review is later needed, use the user's Terra / medium preference.
Preserve the protected supervisor `loop.py` change. Push only reviewed, scoped updates.

## Active execution queue — refreshed 6 September

This queue drives work; the historical evidence below does not close newer gates.
The target remains 9 September WAT. Timeboxes set priority, not permission to
drop requirements or declare an unverified product ready.

### Day 1 — usable runtime and real supervision

- [x] **A. Finish the native release build and verify packaged bytes.**
  Proven for clean source `60ffa76`, checkout `pex-verify-5ee1ee7`: both MSI and
  NSIS built and passed extracted-payload verification. Execs 46349 and 89984
  are terminal. Receipt `build/pex-package-receipt-60ffa76.json`, SHA256
  `8BA32227276F02AAC9F2CA761F700B9F849D1B88604F2DD6F2C006253DF7E0E3`.
  Newly rebuilt bridge lifetime checks: 3 passed. This is a baseline package
  gate, NOT installed UX or final-source approval. Later context fixes are not
  included in these installers; G requires final-source rebuild and verification.
  Acceptance: MSI/NSIS contain the expected desktop and three helpers; retain
  source/hash-bound package receipt and rerun frozen lifetime checks for new bytes.
- [ ] **B. Close the semantic trajectory gap, not only stop-time checks.**
  Authority: recovery spec section 15 and `TRAJECTORY_SEMANTIC_REVIEW.md`.
  Current: P0 OPEN; durable opt-in dispatch cap exists, but material mid-task
  review now has a first bounded repeated-command-failure path with durable
  coalescing, exact evidence and local/remote independent-verifier enforcement.
  Broader material signals, pacing, complete model-use accounting and live proof
  remain open. See `TRAJECTORY_SEMANTIC_REVIEW.md` for source gates and limits.
  Acceptance: shared local/remote eligibility, evidence-bound decisions, quiet
  routine progress, bounded review and same-worker outcome. Mocked tests first;
  live proof is separate. The user approved narrow `loop.py` edits while
  preserving its existing change on 6 September; integration is now actionable.
  Do not enable global force-LLM or bypass the protected file through another path.
- [ ] **C. Reproduce and repair the actual native startup/retry failure.**
  Acceptance: release cold start, retained failure diagnostics, normal Retry,
  close/reopen and persisted setup work without orphan bridge processes.
  Frozen helper tests are supporting evidence, not native-window proof.
  Native interaction currently requires renewed permission; do not steal PC focus.

### Day 2 — complete human-facing flows

- [ ] **D. Finish actual-UI onboarding and all eight pets.**
  Current follow-up: compact status message dismissal repaired (195 frontend
  tests and production build passed). Source-only eight-pet contact sheets
  inspected; Drift jumping frame 0 has a visually flat-cut lower body despite
  transparent cell margins. Retain `build/pet-source-audit-5c00433`, including
  exact exported Drift frames. No sprite edits or native playback approval.
  Acceptance: goal, connection, BYOK and supervisor setup are understandable;
  each pet animates without an opaque background; dismissing a message and
  hiding/restoring the pet are distinct and persist correctly after restart.
  Include empty, disconnected, working, needs-human and exhausted-review states.
- [ ] **E. Verify supported harness and permission flows.**
  Acceptance: real Codex/Cursor/OpenCode support matches labels; correction,
  approvals, escalation and overlay reversal preserve the existing worker.
  Retain exact receipts without changing unrelated user sessions.
- [ ] **F. Complete restraint/recovery and integration evidence.**
  Quiet denominator remains ten: four quiet successes, two inconclusive,
  one early false escalation, three pending. Preserve failures; do not restart
  prepared Q08. Resume model runs only after resolving the current quota pause.
  AgentCore remains a spec target under the no-card-charge boundary, not an
  excuse to deploy without verified coverage. No mock is live integration proof.

### Day 3 — freeze, demonstrate, review submission

- [ ] **G. Run the complete regression on final clean sources.**
  Clean `d7b3a64` full gate passed: 3,903 passed, 13 skipped, zero failures/errors;
  exec 16849 is terminal. Receipt/hash in handoff. This excludes later Settings,
  compact dismissal and trajectory updates, so G stays open. Include frontend/Rust,
  package integrity and installed/fresh-profile smoke after final code changes.
- [ ] **H. Finish honest benchmark and code-audit closure.**
  Acceptance: equivalent prompts/environments, no evaluator leakage, failed
  runs and PEX overhead retained; full spec/audit coverage checked, not inferred
  from counts. No fixture-derived productivity headline or invented ranking.
- [ ] **I. Produce the judge-facing demo and exact submission package.**
  Acceptance: reproducible setup, truthful support matrix, architecture and
  curated real recovery trace; <=5-minute video; rules/bonus evidence rechecked.
  Show exact final artifacts to the user and obtain attempt-specific submission
  confirmation. The demo cannot claim unverified behavior.

Execution rule: finish a critical-path item or expose its concrete missing
dependency, then move to the next safe item. Avoid repeated documentation-only
cycles, duplicate builds, or broad test reruns before relevant product repairs.
Keep the full goal active; NO-GO until all required gates have direct evidence.

Official read-only recheck on 6 September: the
[rules](https://agentsforhumans.devpost.com/rules) list 14 September, 5 PM PDT as
the organizer's deadline. We keep the earlier 9 September internal target.
The [project gallery](https://agentsforhumans.devpost.com/project-gallery) is not
published yet, so no public ranked comparison was available there. Use the specs,
judge criteria and retained live evidence as the quality bar; do not invent a rank.
AgentCore is encouraged but not required by those official rules; it remains in
our build-spec target, subject to the user's no-card-charge authorization.

## 1. Core product and reliability — first gate

- [x] Real shared Codex thread inspected and confirmed without creating its work.
- [x] Repair pre-event worker visibility so its goal can be attached first.
- [x] Persistent goal and scoped correction grant accepted by production HTTP API.
- [x] Real Strands + independent verifier generated a specific correction.
- [x] Correction reached the existing thread; worker produced exact `shipped\n`.
- [x] Subsequent Strands decision was NOOP, not another warning.
- [x] Grant revoked and observer detached; worker remains readable, idle, three
  total turns (one baseline warm-up, one controlled stop, one PEX correction).
- [x] Repair and recapture missing causal outcome/worker-response audit fields
  (clean 4543a58 run-03, independently reviewed, terminal helped=true).
- [x] Retain a separate production-path correct-completion silence case
  (clean 4543a58 run-04, independently reviewed, real Strands NOOP).
- [x] Retain fresh false-claim recovery through exact observed test evidence
  (clean `ee459f8` run-07; independent receipt audit passed).
- [x] Complete worker-mediated uncertain-evidence live case (clean `5ff58f6`,
  independently reviewed run-09: gather, scoped request, actual passing tests, NOOP).
- [ ] Complete ten varied quiet-task live cases and measure false-positive rate.
- [x] Reject wrong-directory Codex pytest evidence at normalization and receipt matching.
- [x] Repair disconnected consumer re-block after cancellation-safe settlement.
- [x] Retain bounded oversized shared command observations without manufacturing
  complete test evidence (reviewed offline; fresh live recapture remains open).
- [x] Rerun full clean-source Python after directory/shutdown repairs: `84d9bd3`,
  3,691 passed / 29 skipped / one warning, not warning-clean release proof.
- [x] Repair fixture ownership and complete a strict full clean gate (`f529644`:
  3,718 passed, 27 skipped, zero failures/errors or thread-warning recurrence).
- [x] Verify probe-reference repair on clean sources (231 affected tests) and a
  new live uncertain case (run-09); preserve run-08's failed evidence.
- [ ] Diagnose native post-start bridge failure; retain original failure code.
- [ ] Repeat cold start, normal retry and restart persistence on release sources.

The controlled report case proves transport/recovery behavior only. It is not an
organic failure example, benchmark score or measured productivity improvement.
Historical source-1e645cd evidence remains under the clean worktree's ignored
`build/shared-demo-client-receipts-02`; fresh source-4543a58 recovery and quiet
receipts are in sibling run-03 and run-04 directories. Never publish credentials
or raw private worker state. An exact artifact is not a substitute for complete
audit fields. See the sanitized `demo/evidence/LIVE_CODEX_STRANDS_2026-09-06.md`.

## 2. Product experience and integration evidence — second gate

- [x] Eight native roster previews render at normal window size after recovery.
- [x] Native message dismissal leaves pet visible; pet close saves hidden state.
- [x] Floating pet no longer claims all quiet on an empty connected profile.
- [ ] Verify all eight animations/transparency and restoration after restart.
- [ ] Exercise goal/connection/supervisor setup from the actual UI; remove
  confusing developer-centric wording without hiding real capability limits.
- [ ] Run remaining Cursor/OpenCode and cross-harness flows with honest support
  labels and exact live receipts. Never modify unrelated active user sessions.
- [ ] Verify routine approvals, human escalation and reversible overlay paths.
- [ ] Establish AgentCore access without card charges before deployment. Credits
  or a budget alarm alone are not a guarantee of no billing.

## 3. Release and presentation — final gate

- [ ] Freeze fair benchmark prompts/environments and run authorized paired arms;
  include failed runs, PEX overhead and limits. No headline from fixture scores.
- [ ] Clean-source full tests, build/package integrity and fresh-profile smoke.
- [ ] Final installed-build UI and backend review, not only dev-server tests.
- [ ] Curated real traces, architecture, reproducible setup and support matrix.
- [ ] Public demo video at most five minutes; label recorded replay explicitly.
- [ ] Recheck official rules, submission fields and existing bonus-post evidence.
- [ ] Review exact submission artifacts with user; obtain final submission
  confirmation before the irreversible submission step.

Do not claim perfection or a guaranteed win. Mark a box only with retained
evidence tied to its source revision. If a gate fails, repair the cause and rerun
the affected gate; do not erase the failure or weaken the specs to hit the date.
