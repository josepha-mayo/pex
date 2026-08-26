# PEX — IMPLEMENTATION RECOVERY SPEC
## Stop Building Around PEX. Build PEX.

**Purpose:** Correct the current implementation direction immediately.

The current behavior is not PEX.

Sending a generic message like:

> `PEX: a completion claim is contradicted by current state (no matching test/artifact evidence). Verify with the required command and report the actual output.`

to every completed session is not supervision.

It is a completion hook with a canned warning.

That behavior must be removed.

PEX must become a real independent supervisor that understands the user's persistent goal, observes what the worker actually did, gathers evidence, decides whether intervention is needed, and either takes a specific justified action or remains silent.

---

# 0. STOP FEATURE WORK

Do not add more integrations.

Do not add more UI.

Do not add more Docker infrastructure.

Do not add more WSL setup.

Do not add more Tauri polish.

Do not add more notifications.

Do not add more benchmark tasks.

Do not add more generic rules.

Do not add more "PEX says..." templates.

Do not claim completion.

Until the core closed loop below works on a real Codex session, everything else is secondary.

The next milestone is exactly one thing:

> **A real Codex session is observed by a real PEX supervisor. PEX reasons over the persistent goal and actual state, then either returns NOOP or sends a specific evidence-grounded intervention.**

Nothing else counts as progress toward the core product.

---

# 1. DELETE THE CURRENT FAKE BEHAVIOR

Remove any logic equivalent to:

```python
if session_completed:
    send_generic_pex_warning()
```

Remove any rule that automatically sends a warning merely because:

- a session ended;
- the agent used the word "done";
- no test event was seen;
- no artifact matched a simplistic pattern;
- a stop event occurred.

A stop event is only a trigger to **inspect**.

It is not proof of failure.

A missing observed test command is not automatically proof that the task is incomplete.

The correct default is:

> **NOOP unless evidence justifies intervention.**

Silence is a valid and often ideal PEX action.

---

# 2. WHAT PEX MUST DO AT SESSION STOP

When Codex stops or claims completion:

```text
STOP EVENT
   ↓
load persistent goal
   ↓
load acceptance criteria
   ↓
extract actual claims made by worker
   ↓
inspect real observable state
   ↓
determine what evidence is required
   ↓
collect available evidence
   ↓
reason:
   - supported?
   - contradicted?
   - uncertain?
   ↓
choose:
   - NOOP
   - gather more evidence
   - send specific correction
   - ask human
   ↓
observe what happens next
```

This must be real.

Do not skip directly from "stop event" to "send message."

---

# 3. PERSISTENT GOAL IS REQUIRED

PEX needs a durable task record for every supervised worker.

Minimum schema:

```json
{
  "goal_id": "...",
  "session_id": "...",
  "objective": "...",
  "acceptance_criteria": ["..."],
  "constraints": ["..."],
  "non_goals": ["..."],
  "required_evidence": ["..."],
  "important_decisions": ["..."]
}
```

If there is no persistent goal attached to a session, PEX must not pretend it understands completion.

It may observe, summarize, or ask the user to attach/confirm a goal if necessary.

It may not invent acceptance criteria.

---

# 4. ACTUAL CLAIM EXTRACTION

PEX should not assume every stopped worker claimed "everything is complete."

Extract what the worker actually asserted.

Examples:

> "Implemented the parser and tests pass."

Claims:

- parser implemented;
- tests pass.

> "I updated the config. I did not run integration tests."

Claims:

- config updated;
- integration tests not verified.

> "The requested migration is complete."

Claim:

- migration complete.

Store structured claims with source message IDs and confidence.

Use deterministic parsing where possible and semantic extraction where needed.

---

# 5. EVIDENCE MODEL

For each claim, PEX should ask:

> What observable evidence would support or contradict this?

Examples:

### Claim: "All tests pass."

Possible evidence:

- test command executed after relevant code changes;
- exit code 0;
- expected test suite count;
- no later edits invalidated that run.

### Claim: "Evaluation completed."

Possible evidence:

- output artifact exists;
- expected row count exists;
- process exited successfully;
- required metrics were produced;
- no missing shards/tasks.

### Claim: "Bug is fixed."

Possible evidence:

- reproduction fails before fix;
- same reproduction passes after fix;
- relevant regression test passes.

### Claim: "Deployment is live."

Possible evidence:

- deployment command succeeded;
- endpoint responds;
- health check passes.

PEX should have typed evidence providers for test results, file existence/count, Git diff, process state, service health, artifact metadata, command history, and session events.

Do not rely on worker narration when external state exists.

---

# 6. REAL SUPERVISOR INFERENCE

PEX must invoke a real model through the intended Strands/AWS supervisor path for semantic decisions.

There must be logs proving:

```text
event received
goal loaded
claims extracted
evidence gathered
supervisor inference called
structured decision returned
policy applied
action executed
```

Suggested structured supervisor output:

```json
{
  "decision": "NOOP | INTERVENE | GATHER_EVIDENCE | ASK_HUMAN",
  "diagnosis": "...",
  "evidence_refs": ["..."],
  "confidence": 0.0,
  "recommended_action": {
    "type": "...",
    "message": "..."
  }
}
```

The model must not receive benchmark oracle information.

The model must reason from legitimate state.

---

# 7. NO GENERIC INTERVENTION TEXT

PEX interventions must cite the actual problem.

Bad:

> "Completion is contradicted by current state. Verify."

Bad:

> "Please run tests and report actual output."

Bad:

> "Do not stop until requirements are complete."

Good:

> `You marked the task complete, but acceptance criterion 3 requires 30 evaluation rows. results.jsonl currently contains 27. Missing task IDs: 11, 18, 24. Resume the evaluation and verify the final row count before stopping.`

Good:

> `You said the test suite passes. The latest observed pytest run exited 1 after your final edit to src/parser.py. Failing test: tests/test_parser.py::test_nested_array. Continue from that failure.`

Good:

> `The requested API endpoint exists, but the acceptance criterion requires HTTP 200 from /health. The local service currently returns 500 with "missing DATABASE_URL". Resolve that before declaring completion.`

Every intervention should be specific, evidence-backed, relevant to the goal, actionable, and minimal.

---

# 8. NOOP MUST BE A FIRST-CLASS ACTION

PEX should frequently do nothing.

Example:

Agent stops.

PEX checks:

- acceptance criteria satisfied;
- tests pass;
- artifact exists;
- no unresolved blockers.

PEX action:

```json
{
  "decision": "NOOP",
  "diagnosis": "Completion is supported by current evidence."
}
```

Do not send congratulations unless the user explicitly enables them.

Do not inject useless text into completed chats.

A good supervisor is quiet when no supervision is needed.

---

# 9. GATHER MORE EVIDENCE BEFORE NAGGING

If PEX is uncertain, do not immediately send a warning.

First use available tools.

Example:

Worker says tests pass but no test result is visible.

If PEX can safely run or inspect the test:

```text
PEX verifies test
→ exit 0
→ NOOP
```

If it fails:

```text
PEX obtains exact failure
→ sends specific intervention
```

If verification would be destructive or expensive:

```text
PEX asks human or worker for needed evidence
```

The product must reduce interruptions, not manufacture them.

---

# 10. CONTINUATION BEHAVIOR

If PEX concludes work is incomplete, it must send a real follow-up to the existing worker session and observe the result.

Example:

```text
Codex stop
→ PEX detects 27/30 rows
→ PEX sends exact missing rows
→ Codex resumes
→ PEX continues observing
→ Codex produces 30/30
→ PEX verifies
→ NOOP
```

Do not call it done because the message was sent.

The intervention outcome matters.

---

# 11. INTERVENTION AUDIT LOG

Every intervention must record:

```json
{
  "session_id": "...",
  "goal_id": "...",
  "trigger_event": "...",
  "claims": [],
  "evidence": [],
  "supervisor_model": "...",
  "inference_request_id": "...",
  "diagnosis": "...",
  "decision": "...",
  "action": "...",
  "worker_response": "...",
  "outcome": "...",
  "helped": true
}
```

For any PEX message, the developer must be able to answer:

1. What event triggered inspection?
2. What was the actual goal?
3. What did the agent claim?
4. What evidence existed?
5. Why was intervention necessary?
6. Why was this exact intervention chosen?
7. What happened afterward?

If those cannot be answered, the intervention is not acceptable.

---

# 12. BUILD ONE REAL CODEX LOOP FIRST

Do not broaden scope until this works.

Required Codex milestone:

1. PEX discovers or attaches to a real Codex session.
2. PEX receives actual session events.
3. User attaches a real persistent goal and criteria.
4. PEX can inspect repo, diff, tests, artifacts, and process state.
5. A real Strands supervisor call occurs.
6. PEX returns NOOP, GATHER_EVIDENCE, INTERVENE, or ASK_HUMAN.
7. If intervention is needed, it reaches the same Codex session.
8. PEX watches the worker continue.
9. PEX determines whether the intervention solved the issue.

Only when all nine steps work is the core Codex loop complete.

---

# 13. REQUIRED CODEX DEMO TESTS

## Test 1 — Correct completion

Worker genuinely completes the task.

Expected PEX:

- inspect;
- verify;
- **NOOP**.

Failure condition:

PEX sends a generic warning.

## Test 2 — Premature stop

Worker intentionally stops after only part of the acceptance criteria.

Expected PEX:

- detect exact missing criterion;
- gather exact evidence;
- send specific continuation;
- observe worker continue;
- verify final completion.

## Test 3 — False test claim

Worker says tests pass after a failing run.

Expected PEX:

- identify latest relevant test evidence;
- cite exact failure;
- intervene.

## Test 4 — Uncertain claim

Worker says complete but PEX lacks enough evidence.

Expected PEX:

- gather evidence first;
- if evidence supports completion → NOOP;
- if evidence contradicts → specific intervention.

## Test 5 — No pointless nagging

Run ten correctly completed tasks.

PEX should not send ten warnings.

False-positive rate must be measured.

---

# 14. HARD FALSE-POSITIVE BAR

The current implementation has effectively a 100% intervention rate at completion.

That is unacceptable.

Optimize for high-value intervention and low unnecessary interruption.

Measure:

```text
intervention_precision = useful_interventions / all_interventions
```

Do not increase recall by spamming every stopped worker.

---

# 15. DRIFT DETECTION COMES AFTER COMPLETION LOOP

Once stop/completion supervision is real, add trajectory supervision.

Required behavior:

```text
recent events
+ persistent goal
+ recent verified progress
+ repeated actions
+ dependency state
→ supervisor
→ NOOP or specific intervention
```

Signals can include:

- repeated same failing command;
- repeated semantically identical searches;
- many actions with no new artifact/test evidence;
- unrelated broad refactor;
- downstream step before prerequisite exists;
- forgotten constraint;
- context degradation;
- duplicate investigation already completed elsewhere.

Detection is not intervention. PEX reasons whether intervention is worth it.

---

# 16. CONTEXT HANDOFF MUST BE REAL

Do not implement:

```python
send_predefined_fact_to_agent()
```

Required:

```text
Agent A discovers fact
→ event/transcript/artifact enters PEX context store
→ fact is stored with provenance
→ Agent B later works on related goal
→ PEX computes relevance
→ PEX creates minimal context bundle
→ sends to Agent B
→ records handoff
```

No benchmark metadata.

No human-authored hidden hint.

---

# 17. USER PROMPT CORRECTION

After the core loop works, implement persistent-intent conflict detection.

Flow:

```text
new user prompt
→ compare to active goal/constraints/decisions
→ classify:
   consistent
   refinement
   possible contradiction
   explicit override
→ if consequential contradiction:
   ask user before forwarding
```

PEX should not rewrite normal prompts unnecessarily.

Avoid becoming an annoying grammar/prompt assistant.

---

# 18. APPROVAL BROKER

After core supervision works, safe routine actions may be auto-approved under local policy.

Possible safe routine actions:

- pytest;
- npm test;
- cargo test;
- lint;
- typecheck;
- local build.

Potentially dangerous actions:

- destructive deletes;
- force push;
- production deploy;
- schema migration;
- secret export;
- billing/spend;
- public posting.

Dangerous actions require explicit policy or human confirmation.

Policy is local and cannot be bypassed by the cloud model.

---

# 19. JIT HARNESS COMPILER

Do not implement this as "append more prompt text."

A harness overlay may change:

- tools;
- MCP;
- model;
- reasoning effort;
- context bundle;
- permissions;
- system/project instructions;
- verification policy;
- sandbox/worktree;
- token budget.

Every overlay must be justified, scoped, reversible, and logged.

PEX should apply an overlay only when evidence suggests current configuration is hurting progress.

---

# 20. PET UI COMES AFTER CORE LOOP

The pet is the face of the supervisor.

It is not the supervisor.

Do not use UI polish to hide missing intelligence.

Minimum useful states:

```text
3 working · 0 need you
Codex incomplete → fixing
Cursor context shared
1 decision needs you
PEX offline
```

If PEX has no real evidence, do not display confident claims.

---

# 21. DO NOT REQUIRE USER TO MOVE INTO PEX

PEX must supervise existing harnesses.

The user should still open Codex, Cursor, Claude Code, OpenCode, Devin, etc.

PEX lives above them.

Do not solve integration difficulty by forcing all work to originate from a PEX-owned coding environment.

That changes the product into another harness.

---

# 22. ADAPTER ORDER

Only after Codex core loop passes:

1. Cursor
2. OpenCode
3. Claude Code
4. Grok Build
5. OMP / Pi
6. Qwen Code
7. Kimi Code
8. Hermes
9. Devin
10. remaining harnesses

Use real structured interfaces such as APIs, App Server, ACP, hooks, plugins, SDKs, and SSE.

Avoid screen scraping where native control exists.

---

# 23. BENCHMARK IS BLOCKED UNTIL CORE PRODUCT PASSES

Do not run or report new headline benchmark results while "PEX" is still a generic message hook.

Before benchmark work resumes, prove:

- real supervisor inference;
- real state inspection;
- real NOOP;
- real specific intervention;
- real intervention outcome;
- no privileged prompt;
- no stressor leakage.

Then run:

- Cursor baseline;
- Cursor + PEX;
- Codex baseline;
- Codex + PEX.

Same initial task information within harness.

PEX differs only because the real supervisor is attached.

---

# 24. BENCHMARK ABSOLUTE RULE

PEX gets:

- goals;
- normal project state;
- worker events;
- legitimate context;
- normal tests;
- supervised other-agent context.

PEX never gets:

- hidden evaluator;
- stressor label;
- expected supervisor action;
- oracle fact;
- solution;
- treatment-only hint.

If PEX knows the answer because the benchmark runner told it, the run is invalid.

---

# 25. REQUIRED TEST SUITE BEFORE CLAIMING "PEX WORKS"

Do not say "done" until these pass.

## Core

- [ ] Real Codex session attaches.
- [ ] Events stream.
- [ ] Persistent goal attaches.
- [ ] Claims extract.
- [ ] Evidence providers work.
- [ ] Real Strands/model inference executes.
- [ ] Structured decision produced.
- [ ] NOOP works.
- [ ] Specific intervention works.
- [ ] Follow-up reaches same session.
- [ ] Outcome is observed.
- [ ] Audit log is complete.

## Behavior

- [ ] Correct completion produces silence.
- [ ] Premature stop produces specific correction.
- [ ] False test claim is contradicted with exact evidence.
- [ ] Uncertain state triggers evidence gathering before warning.
- [ ] PEX does not spam every completed chat.
- [ ] PEX does not invent acceptance criteria.
- [ ] PEX does not send generic boilerplate as evidence.

## Safety

- [ ] Wrong session never receives intervention.
- [ ] Dangerous approval is not silently approved.
- [ ] Cloud failure does not bypass local policy.
- [ ] PEX intervention can be disabled.
- [ ] Reversible actions can be undone.

## Integrity

- [ ] No hidden benchmark data reachable.
- [ ] No task-specific canned intervention.
- [ ] No condition-specific prompt suffix.
- [ ] All interventions trace to real observed evidence.

---

# 26. DEMO BAR

The first acceptable internal demo is not a pet animation.

It is this:

```text
User gives Codex a real task.

Codex works.

Codex stops prematurely.

PEX independently:
  - reads goal;
  - notices exact unmet criterion;
  - gathers exact evidence;
  - calls real supervisor;
  - decides to intervene;
  - sends exact correction.

Codex resumes.

Codex fixes it.

PEX verifies completion.

PEX says nothing further.
```

Then immediately run a second task where Codex genuinely completes correctly.

PEX must inspect and remain silent.

Those two demos together prove PEX can distinguish incomplete from complete.

If it cannot distinguish those, it is not yet a supervisor.

---

# 27. ENGINEERING DISCIPLINE

Maintain `STATUS.md` with only verified status.

Every "works" entry must cite a test, log, screenshot, reproducible command, or recorded demo.

Maintain `PEX_INTERVENTION_LOG.jsonl` for supervisor decisions.

Maintain `KNOWN_FAILURES.md`.

Do not hide failures.

Do not declare milestones complete from code existence alone.

---

# 28. HOW TO USE MODELS

Do not send every event to a giant model.

Pipeline:

```text
raw event
→ normalize
→ deterministic filters/features
→ gather relevant state
→ semantic inference only when needed
→ action
```

Deterministic examples:

- exit code;
- file count;
- missing file;
- repeated command;
- process alive;
- diff exists.

Semantic examples:

- drift;
- relevance;
- user intent conflict;
- whether context should transfer;
- whether current work is useful toward goal;
- how to phrase the correction.

---

# 29. QUALITY STANDARD FOR AN INTERVENTION

Before PEX sends anything, it should pass:

### Relevance
Is this actually relevant to the persistent goal?

### Evidence
Do we have evidence?

### Necessity
Can PEX resolve this silently instead?

### Specificity
Does the message name the actual issue?

### Actionability
Can the worker act immediately?

### Risk
Could this intervention make the trajectory worse?

### Cooldown
Are we repeating ourselves?

If not, choose NOOP or gather more evidence.

---

# 30. WHAT "DONE" MEANS FOR THIS RECOVERY

Do not say the recovery is complete because:

- files were created;
- Docker runs;
- Tauri launches;
- PEX hooks fire;
- Codex receives a message;
- the model API responds;
- one test passes;
- the pet animates.

Recovery is complete only when:

1. Codex genuinely complete task → PEX verifies → NOOP.
2. Codex genuinely incomplete task → PEX identifies exact missing state → real supervisor inference → specific intervention → Codex continues → final state verified.
3. Audit trail proves the entire chain.
4. No canned completion warning remains.
5. No privileged benchmark context is involved.

---

# 31. THE PRODUCT AGAIN, BECAUSE THIS MUST NOT DRIFT

PEX is:

> **an independent supervisor for AI workers.**

It watches agents the user already uses.

It understands persistent human intent.

It observes actual work.

It distinguishes progress from narration.

It gathers evidence.

It transfers context.

It catches drift.

It handles routine supervision.

It asks the human only when necessary.

It adapts the harness when useful.

It verifies outcomes.

It learns how the user's agents behave.

Most importantly:

> **PEX thinks before it interrupts.**

The current "warn every completed session" behavior is the opposite of the product.

Remove it.

Build the closed loop.

Do not add anything else until it is real.
