# PEX — Adaptive Supervisor for AI Agent Work
## Product, Architecture, Implementation, Benchmark, Testing, and Hackathon Specification
**Working document for implementation with Grok 4.6**  
**Hackathon:** AWS + Devpost “Agents for Humans Hackathon”  
**Target track:** Professional Agents  
**Spec status:** Build-driving v1, August 25, 2026

---

# 0. MASTER IMPLEMENTATION PROMPT FOR GROK 4.6

You are the principal engineer, product engineer, systems architect, and test owner for **PEX**, a new AI product being built for the AWS/Devpost **Agents for Humans Hackathon**.

Read this entire specification before changing code.

Your job is not to mechanically follow it. Your job is to understand the product thesis, preserve the hard requirements, improve weak design decisions, investigate current APIs and source code where the spec is stale, and drive the project to a polished, benchmarked, end-to-end working submission.

## Operating freedom

You have broad freedom to:

- change architecture when evidence supports a better design;
- replace libraries, languages, protocols, storage layers, models, or UI implementation;
- reorganize modules and repository structure;
- add features that strengthen the product thesis;
- improve prompts, policies, algorithms, adapters, benchmarks, tests, and UX;
- exploit official SDKs, hooks, ACP, MCP, APIs, local protocols, plugins, extensions, PTYs, process APIs, accessibility APIs, browser automation, or source-level integration where appropriate;
- use subagents for research, implementation, testing, and independent review;
- write helper scripts, probes, adapters, fixtures, test harnesses, and instrumentation;
- choose the best current AWS/Bedrock models and AgentCore components after measuring them;
- investigate any harness directly rather than trusting this document when its interface has changed.

## The one directional constraint: do not go backwards

Do not “solve” a hard problem by degrading the product into a passive dashboard, notification tray, generic multi-agent orchestrator, wrapper around one harness, chat UI, or mock demo.

Do not silently remove capabilities because an implementation is difficult.

Do not disable failing tests, weaken acceptance criteria, fake integrations, fake benchmark outcomes, fabricate telemetry, or present mocked control as real control.

Temporary stubs are permitted during development only when clearly marked and tracked. They must not survive in the final demonstrated path.

When blocked by a vendor limitation, preserve the product abstraction, implement the strongest legal/technical fallback available, expose the capability limitation honestly, and continue improving other paths.

## Development behavior

1. Never declare a milestone complete from self-report alone. Run its acceptance tests.
2. Do not stop a development turn merely because a sub-step is finished if the current milestone remains achievable.
3. Avoid unnecessary clarification requests. Inspect the code, docs, runtime, or APIs first.
4. Before relying on a third-party harness interface, confirm the current official docs/source.
5. Keep `STATUS.md` current with:
   - current milestone,
   - what works,
   - what is broken,
   - evidence/tests,
   - next actions,
   - external blockers.
6. Keep `DECISIONS.md` for consequential architecture/product decisions and why.
7. Keep `INTEGRATIONS.md` with a live capability matrix for every supported harness.
8. Keep `BENCHMARKS.md` and machine-readable raw benchmark outputs. Never edit raw results by hand.
9. Checkpoint risky changes using Git before large refactors.
10. Prefer root-cause fixes over patches that merely hide symptoms.
11. If a feature causes regression elsewhere, fix the interaction rather than simply removing the feature.
12. Continuously test the actual user experience, not only isolated functions.
13. Use deterministic code for deterministic judgments. Spend LLM reasoning only where semantic judgment is genuinely needed.
14. Treat human attention as the system’s most expensive resource.
15. PEX must be useful while the user continues using their existing harnesses. Do not force migration into a PEX-owned coding harness.

## Definition of success

PEX succeeds when a person can run several independent AI coding agents in tools they already use, give PEX the persistent goal of each job, and stop doing most of the tedious management work themselves.

PEX should observe those agents, understand what they are trying to accomplish, preserve and transfer context, detect drift/stagnation/premature completion, nudge or reconfigure the agents, handle low-risk approvals under policy, verify claims, optimize their harness configuration, and interrupt the human only for real decisions.

The final submission must include an empirical benchmark showing the delta in task success and human-management burden for:

- Cursor without PEX
- Cursor with PEX
- Codex without PEX
- Codex with PEX

The central claim is not “PEX makes models smarter.”

The central claim is:

> **PEX turns the human from a full-time manager of AI agents into the owner of goals and decisions.**

---

# 1. PRODUCT THESIS

## 1.1 Problem

As coding agents become genuinely useful, a new category of repetitive human labor has appeared: **managing the agents themselves**.

A user running several long-lived sessions currently has to perform tasks such as:

- remember the true goal of each session;
- notice when an agent is drifting away from that goal;
- remind an agent of constraints it forgot;
- notice when a long-running agent has stalled;
- notice when it ended a turn before the actual goal was complete;
- distinguish genuine progress from convincing narration;
- answer repetitive permission requests;
- decide whether an approval is safe;
- copy useful context from one agent to another;
- ask one agent to summarize for a new agent;
- recover context that was compacted or lost;
- choose which harness/model should take a new task;
- compare conflicting recommendations from multiple agents;
- tell an agent to keep working;
- catch dependency-order mistakes before they cost hours;
- catch generic, low-value work that does not serve the actual goal;
- detect repeated reads/searches/retries that waste tokens;
- restart or hand off a degraded long-context session;
- clean temporary files/worktrees/processes after agents move on;
- monitor several windows just to know which one needs attention;
- interrupt a working agent merely to ask “what is happening?”;
- remember why an earlier architectural decision was made;
- carry the human’s intent consistently across Cursor, Codex, Claude Code, Devin, OpenCode, and other tools.

This work is fragmented, repetitive, judgment-heavy, and increasingly expensive in human attention.

## 1.2 Product

PEX is a **goal-aware adaptive supervisor that lives above existing AI agent harnesses**.

It is not another coding harness.

It is not merely a fleet dashboard.

It is not merely a verifier.

It is not merely a context manager.

PEX attaches to agent sessions the user already runs and makes the overall human-agent system behave coherently.

The user owns:

- goals;
- priorities;
- consequential decisions;
- irreversible or high-risk approvals.

PEX owns as much as safely possible of:

- observation;
- context logistics;
- nudging;
- verification;
- routine approvals;
- harness adaptation;
- cross-agent handoffs;
- drift recovery;
- repetitive cleanup;
- progress reporting;
- escalation timing.

## 1.3 Product metaphor

The visual metaphor is a **small desktop pet/robot supervisor**.

It stays always available without demanding a dashboard.

It can float near or attach to active harness windows.

At a glance it might show:

> `4 working · 1 drifting · fixed`

or:

> `Codex needs a decision`

or:

> `Moved eval context → Cursor`

Clicking expands the detail.

The pet is not the technical innovation. It is the user-facing embodiment of the actual innovation: **an adaptive control layer over the user’s AI workforce**.

---

# 2. HACKATHON CONTEXT AND SCORE TARGET

## 2.1 Verified hackathon facts as of August 25, 2026

Hackathon: **Agents for Humans Hackathon**  
Organizer/Sponsor: AWS, managed by Devpost  
Public page: `https://agentsforhumans.devpost.com/`

Submission deadline:

- **September 14, 2026 at 5:00 PM PDT**
- Submission period began August 10, 2026.

Current public participant count observed on August 25: approximately **5,057**. The number can change.

Prize pool: **$40,000**.

Relevant prizes:

- Grand Prize: **$10,000**
- Professional Agents Gold: **$5,000**
- Professional Agents Silver: **$3,000**
- Professional Agents Bronze: **$2,000**

A project may win one prize.

## 2.2 Required product framing

The official theme asks for a new agent built with **Strands Agents SDK** that does real work for real people and handles it end-to-end rather than merely chatting.

Professional Agents is described as:

> an agent that makes someone dramatically better at the work they already do; target repetitive, judgment-heavy tasks that eat their day.

PEX fits by attacking the emerging repetitive professional task of **managing multiple autonomous software agents**.

## 2.3 Required submission artifacts

The submission currently requires:

- text description;
- public source repository;
- all source/assets/setup instructions;
- README;
- MIT or Apache open-source license;
- architecture diagram;
- public YouTube or Vimeo demo video, maximum **5 minutes**;
- demo must show the working product;
- pitch must explain:
  1. the problem,
  2. who it is for,
  3. why it matters;
- AWS Builder ID;
- functioning test/demo access;
- optional live demo link.

Judges are not required to run the project. They may judge from the video, description, and images, so the video must make the value undeniable.

## 2.4 Judging criteria

Five criteria are equally weighted:

1. **Technical Implementation**
   - thorough and skillful Strands Agents use;
   - non-trivial working implementation;
   - live demo and/or Amazon Bedrock AgentCore deployment strengthens this score.

2. **Design**
   - complete coherent product experience;
   - not merely a technical proof of concept.

3. **Potential Impact**
   - credible, specific real problem;
   - real audience;
   - demonstrated solution actually addresses it.

4. **Creativity & Originality**
   - creative, non-obvious use of Strands Agents;
   - evidence of genuine understanding of the problem.

5. **Presentation**
   - clear end-to-end demonstration;
   - clear problem/audience/importance;
   - easy to follow.

Tie breaks proceed in criterion order, which makes Technical Implementation especially important.

## 2.5 Bonus

Submissions advancing to Stage Two may receive up to **+0.6** points via builder.aws posts, apparently **0.2 each** up to three qualifying posts.

Current official wording requires public builder.aws posts about the AWS build journey. Confirm exact title/tag wording again immediately before publishing because the rules were updated during the event.

## 2.6 AWS credits

Registered entrants can request up to **$50 AWS promotional credit**, while supplies last, through the hackathon flow. Current request deadline is September 11, 2026 at 12 PM PT. Reconfirm before relying on it.

## 2.7 Score-maximizing strategy

PEX should deliberately generate evidence for each criterion.

### Technical Implementation
Show:

- real Strands supervisor loop;
- AgentCore deployment;
- event-driven adapter architecture;
- live Cursor/Codex control;
- memory/state;
- semantic + deterministic supervision;
- policy-based approvals;
- context handoffs;
- trajectory correction;
- dynamic harness adaptation;
- real benchmark telemetry;
- observability/traces.

### Design
Show:

- pet is useful in one glance;
- minimal interruptions;
- clear escalation;
- one-click jump to responsible agent;
- ask PEX instead of disturbing worker;
- expanded control center only when needed;
- polished install/onboarding;
- coherent “goal → autonomous supervision → decision” journey.

### Impact
Show measured:

- task-success lift;
- fewer human interventions;
- less active human management time;
- fewer false-done outcomes;
- lower wasted tokens per successful task if achieved.

### Creativity
Do not sell “multi-agent orchestration.”

Sell:

> **a vendor-agnostic adaptive supervisory layer that modifies and coordinates existing harnesses around persistent human intent.**

### Presentation
Make the 5-minute video primarily a live story, not a slide lecture.

---

# 3. CORE DIFFERENTIATION

Several products can already orchestrate multiple agents, provide shared memory, verify completion, send alerts, or expose dashboards.

PEX must therefore defend a stronger wedge.

## 3.1 The wedge

PEX is a **personal adaptive control plane** whose unit of optimization is neither the individual agent nor the task queue.

Its unit of optimization is:

> **the human + all currently active AI workers + the persistent intent behind their work.**

## 3.2 Strong differentiators

### A. Persistent Intent Ledger
PEX maintains the durable goal above transient prompts and sessions.

### B. Cross-Harness Context Mesh
Context belongs to the project/goal, not to a specific chat window.

### C. Trajectory Prognosis
PEX intervenes before obvious failure, not only after a task fails.

### D. JIT Harness Compiler
PEX can temporarily adapt each agent’s configuration to the current phase/task.

### E. Personal Agent Fingerprints
PEX learns recurring behavioral failure modes of the user’s specific harness/model configurations.

### F. Human-Prompt Correction
PEX can detect when the human’s new instruction conflicts with their own persistent goal.

### G. Attention Brokerage
PEX attempts silent/reversible repair first and escalates only genuine decisions.

### H. Cross-Harness Control
PEX works above independently started tools rather than requiring migration into a PEX-owned runtime.

---

# 4. NON-NEGOTIABLE PRODUCT PRINCIPLES

1. **Existing tools stay usable.** The user can keep Cursor, Codex, Claude Code, Devin, Grok Build, etc.
2. **Goal first, chat second.** Transient chat text cannot silently override persistent intent.
3. **External state beats narration.** “Done” is not trusted merely because an agent says it.
4. **Human attention is expensive.** Avoid avoidable pings.
5. **Autonomy must be reversible where possible.**
6. **Adapters negotiate capability.** Do not pretend every vendor exposes identical control.
7. **No benchmark theater.** All benchmark outputs are reproducible and machine-readable.
8. **No hidden degradation.** If an integration loses capability after a vendor update, surface it.
9. **Context is routed, not dumped.** Give agents the smallest sufficient context.
10. **Progress is evidence-based.** Track artifacts, tests, diffs, process state, and decisions.
11. **The supervisor should not become another agent the user must supervise.**
12. **The pet should be quiet by default.**
13. **Configuration adaptation should be ephemeral/reversible unless the user promotes it to permanent.**
14. **Do not let a model approve actions beyond configured authority.**
15. **Do not optimize only for fewer tokens if task success deteriorates.**

---

# 5. TARGET USERS AND JOBS TO BE DONE

Primary target:

- developers/research engineers/power users running multiple AI coding/research agents in parallel.

Secondary:

- small engineering teams;
- founders managing several autonomous coding tasks;
- ML researchers running code/eval/research agents;
- agent-heavy operations teams.

Primary job:

> “I want to state what I am trying to achieve and spend my attention on real decisions, not babysitting the agents that are supposed to save me time.”

---

# 6. USER EXPERIENCE

## 6.1 Always-on-top pet

Recommended desktop implementation:

- **Tauri 2 + React/TypeScript** for a lightweight cross-platform always-on-top UI;
- transparent window;
- frameless;
- draggable;
- click-through when configured;
- compact default footprint;
- OS-specific window attachment/accessibility modules behind interfaces.

Default compact states:

- sleeping/idle;
- observing;
- working;
- context handoff;
- correcting drift;
- approval handled;
- warning;
- human decision needed;
- degraded integration.

Do not rely only on animation. Every state needs concise accessible text.

Examples:

- `3 agents working`
- `Codex drifting → corrected`
- `Cursor waiting → approved tests`
- `Devin needs you`
- `Context moved → OpenCode`
- `Saved 18k repeated tokens`
- `Goal conflict detected`

## 6.2 Expand behavior

Single click opens a compact inspector:

- current agent/session;
- persistent goal;
- latest meaningful progress;
- what PEX changed;
- why;
- confidence;
- next expected event;
- buttons:
  - Open agent
  - Ask PEX
  - Pause supervision
  - Undo last PEX intervention if reversible
  - Show evidence

Second expansion opens the full command deck.

## 6.3 Command deck

Must not look like generic Kanban software.

Views:

### “Now”
- active sessions;
- one-line goal;
- state: working / blocked / needs decision / drifting / verifying / idle;
- last meaningful evidence;
- intervention count;
- attention required.

### “Decisions”
Only unresolved human judgments.

### “Context”
Graph/list of:
- durable project facts;
- decisions;
- constraints;
- artifacts;
- who currently knows what;
- stale/conflicting context.

### “Interventions”
Audit trail:
- observed condition;
- evidence;
- action;
- resulting state;
- whether it helped.

### “Agents”
Personal fingerprints:
- harness;
- model;
- recurring strengths;
- recurring failure patterns;
- token behavior;
- completion reliability;
- suggested configuration.

### “Bench”
Live benchmark/result explorer.

## 6.4 Ask PEX

The user can ask:

- “what is Codex doing?”
- “which agent is blocked?”
- “why did you message Cursor?”
- “what does Devin know that Codex doesn’t?”
- “which approach looks better?”
- “did the eval actually finish?”
- “what needs me right now?”

PEX answers from its own canonical state/events instead of interrupting the working agent unless fresh information is genuinely required.

## 6.5 Window navigation

`Open agent` should:

- focus the existing window if local;
- navigate to the correct session when possible;
- open a deep link/browser URL for cloud harnesses;
- never create a duplicate session accidentally.

## 6.6 Remote channels

Target:

- Telegram;
- Discord;
- WhatsApp where technically/legally practical;
- optional Slack;
- optional other channels through adapters.

Remote messages should preserve the same attention policy.

Examples:

> `PEX: Cursor finished but hidden tests fail. I sent the failures back. No action needed.`

> `PEX: Devin and Codex disagree on whether to change the schema. This affects persisted data. Choose A/B or tell me your rule.`

Other agents should also be able to address PEX through an MCP/tool/API surface.

---

# 7. HIGH-LEVEL SYSTEM ARCHITECTURE

```text
                           ┌─────────────────────────────────────┐
                           │         PEX Desktop Pet/UI          │
                           │   compact overlay + command deck    │
                           └─────────────────┬───────────────────┘
                                             │ local IPC/ws
                                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PEX LOCAL BRIDGE                                 │
│                                                                             │
│  Session Discovery → Adapter Manager → Event Normalizer → Local Action Bus │
│       │                 │                    │                 │             │
│       │                 │                    ▼                 │             │
│       │                 │              Local State Store       │             │
│       │                 │          SQLite + artifact refs      │             │
│       │                 │                    │                 │             │
│       ▼                 ▼                    ▼                 ▼             │
│  CursorAdapter     CodexAdapter        Context Extractor   Policy Guard     │
│  ClaudeAdapter     OpenCodeAdapter     Workspace Watcher   Secret Filter    │
│  DevinAdapter      ...                 Process Monitor     Reversibility    │
└───────────────────────────────┬─────────────────────────────────────────────┘
                                │ outbound authenticated requests/events
                                ▼
                 ┌──────────────────────────────────────────┐
                 │    AWS BEDROCK AGENTCORE + STRANDS       │
                 │                                          │
                 │  Supervisor Agent / Strands Graph        │
                 │  Intent + Context reasoning              │
                 │  Trajectory prognosis                    │
                 │  Intervention planner                    │
                 │  Harness optimizer                       │
                 │  Independent verifier                    │
                 │                                          │
                 │  AgentCore Runtime                       │
                 │  AgentCore Memory                        │
                 │  AgentCore Observability / CloudWatch    │
                 └──────────────────┬───────────────────────┘
                                    │ proposed typed actions
                                    ▼
                         Local policy enforcement
                                    │
                      allow / deny / ask human
                                    │
                                    ▼
                           Harness intervention
```

The local bridge is authoritative over local side effects.

The cloud supervisor can propose an action but cannot bypass local permissions/policy.

A local-only mode may exist later, but the hackathon path should visibly use Strands and AgentCore.

---

# 8. RECOMMENDED REPOSITORY STRUCTURE

```text
pex/
├─ apps/
│  ├─ desktop/                 # Tauri + React pet and command deck
│  └─ demo/                    # optional hosted/live demonstration surface
├─ services/
│  ├─ bridge/                  # Python local daemon
│  │  ├─ adapters/
│  │  ├─ discovery/
│  │  ├─ events/
│  │  ├─ policy/
│  │  ├─ context/
│  │  ├─ workspace/
│  │  ├─ process/
│  │  └─ api/
│  └─ supervisor/              # Strands agent, AgentCore entrypoint
│     ├─ agents/
│     ├─ tools/
│     ├─ graphs/
│     ├─ prompts/
│     ├─ scoring/
│     └─ memory/
├─ packages/
│  ├─ protocol/                # typed shared schemas
│  ├─ sdk/                     # adapter SDK for third parties
│  └─ widgets/                 # reusable UI
├─ integrations/
│  ├─ cursor-hook/
│  ├─ claude-hook/
│  ├─ hermes-hook/
│  ├─ pi-extension/
│  ├─ omp-extension/
│  └─ ...
├─ benchmarks/
│  ├─ tasks/
│  ├─ runners/
│  ├─ evaluators/
│  ├─ injections/
│  ├─ analysis/
│  └─ results/
├─ tests/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  ├─ e2e/
│  ├─ chaos/
│  └─ benchmark-smoke/
├─ docs/
│  ├─ architecture/
│  ├─ adapters/
│  ├─ threat-model/
│  └─ demo/
├─ STATUS.md
├─ DECISIONS.md
├─ INTEGRATIONS.md
├─ BENCHMARKS.md
├─ README.md
└─ LICENSE
```

Repository structure may change if a better organization is discovered.

---

# 9. CANONICAL DATA MODEL

Use typed schemas, version them, and preserve raw vendor events for debugging.

## 9.1 Goal

```python
Goal {
  id
  project_id
  title
  objective
  acceptance_criteria[]
  constraints[]
  preferences[]
  forbidden_outcomes[]
  priority
  deadline?
  evidence_requirements[]
  created_at
  updated_at
  supersedes?
}
```

## 9.2 Decision

```python
Decision {
  id
  goal_id
  statement
  rationale
  alternatives_rejected[]
  scope
  confidence
  source        # human | agent | inferred
  status        # active | superseded | uncertain
  created_at
}
```

## 9.3 ContextItem

```python
ContextItem {
  id
  project_id
  goal_id?
  kind          # fact, decision, constraint, artifact, result, hypothesis, warning
  content
  source_refs[]
  provenance
  confidence
  relevance_tags[]
  valid_from
  stale_after?
  supersedes?
  sensitivity
}
```

## 9.4 HarnessSession

```python
HarnessSession {
  id
  harness_type
  vendor_session_id
  project_id
  goal_id?
  cwd?
  repo?
  branch?
  model?
  reasoning_effort?
  status
  context_health
  last_activity
  capabilities
  external_url?
  local_window_id?
}
```

## 9.5 HarnessEvent

```python
HarnessEvent {
  event_id
  ts
  harness_type
  session_id
  project_id?
  event_type
  phase
  raw_event_ref
  message_delta?
  tool_name?
  tool_input?
  tool_output_ref?
  command?
  file_paths[]
  diff_ref?
  approval_request?
  token_usage?
  cost?
  process_state?
  error?
  metadata
}
```

## 9.6 Intervention

```python
Intervention {
  id
  session_id
  goal_id
  trigger
  evidence[]
  diagnosis
  proposed_action
  confidence
  risk
  reversible
  authority_required
  action_taken
  result
  helped?       # measured afterward where possible
  created_at
}
```

## 9.7 AgentFingerprint

```python
AgentFingerprint {
  harness
  model
  model_settings_hash
  project_class?
  observed_sessions
  strengths[]
  failure_modes[]
  premature_stop_rate
  repeated_tool_rate
  context_degradation_profile
  approval_behavior
  token_efficiency
  verified_success_rate
  recommended_overlays[]
}
```

---

# 10. UNIVERSAL HARNESS ADAPTER CONTRACT

Every integration implements the same capability-negotiated interface.

Pseudo-interface:

```python
class HarnessAdapter:
    name: str

    async def probe(self) -> AdapterCapabilities
    async def discover_sessions(self) -> list[HarnessSession]
    async def attach(self, session_ref) -> AttachedSession
    async def stream_events(self, session) -> AsyncIterator[HarnessEvent]

    async def read_messages(self, session, since=None)
    async def read_state(self, session)
    async def read_usage(self, session)
    async def read_diff(self, session)
    async def read_permissions(self, session)

    async def send_message(self, session, text, attachments=None)
    async def inject_context(self, session, context_bundle)
    async def respond_permission(self, session, request_id, decision)
    async def stop(self, session)
    async def continue_or_resume(self, session)
    async def start_session(self, project, prompt, config=None)
    async def fork_or_fresh_handoff(self, session, context_bundle)

    async def get_runtime_config(self, session)
    async def apply_overlay(self, session, overlay)
    async def revert_overlay(self, overlay_id)

    async def focus_ui(self, session)

    async def health(self)
```

## 10.1 Capability object

Never assume parity.

```python
AdapterCapabilities {
  observe_messages
  observe_thought_events
  observe_tool_calls
  observe_file_edits
  observe_shell
  observe_context_compaction
  observe_tokens
  observe_permissions
  observe_session_status

  send_message
  inject_context
  approve
  deny
  start
  stop
  resume
  fork
  summarize
  modify_config
  modify_system_instructions
  modify_tools
  modify_mcp
  modify_model
  modify_reasoning_effort
  focus_ui

  control_granularity   # event, turn, session, UI-only
  trust_level
}
```

The supervisor must condition actions on supported capabilities.

---

# 11. INTEGRATION STRATEGY

Use this order of preference:

1. Official structured server/API/SDK.
2. ACP or another bidirectional protocol.
3. Official lifecycle hooks/plugins/extensions.
4. Official headless JSON mode + session APIs.
5. Stable local session/event storage.
6. Controlled PTY/process integration.
7. OS accessibility/browser automation as a fallback only.
8. Screen scraping only as last resort and never presented as equivalent to a native adapter.

Every adapter gets contract tests.

---

# 12. TARGET HARNESS MATRIX

All listed harnesses are product targets. Cursor and Codex are the benchmark reference implementations and must be especially deep. Do not treat the list below as a cap.

The implementation agent must re-check current documentation and source before coding each adapter.

## 12.1 Cursor — deep target

Current useful surfaces:

- Cursor Hooks can observe/control lifecycle stages.
- Hooks expose events such as:
  - session start/end;
  - pre/post tool use;
  - shell;
  - MCP;
  - file reads/edits;
  - before prompt submit;
  - context compaction;
  - stop;
  - agent response/thought;
  - subagent lifecycle.
- Hooks use JSON over stdin/stdout and can block/modify behavior in appropriate phases.
- Hook input can include stable conversation IDs and transcript paths.
- Cursor CLI supports:
  - interactive and headless modes;
  - session list/resume;
  - worktrees;
  - cloud handoff.
- Cursor CLI supports **ACP over stdio** for custom client integrations.

PEX plan:

- install a small PEX hook package;
- forward normalized hook events to local bridge;
- use ACP/CLI control for sending messages and session control where possible;
- use `beforeSubmitPrompt` for prompt correction/context injection;
- use `stop` for premature-completion gating;
- use pre-tool hooks for high-risk policy checks;
- use `preCompact` to checkpoint durable context before compaction;
- use transcript path only as supplementary evidence, not the only integration.

## 12.2 OpenAI Codex — deep target

Current useful surface:

- Codex App Server exposes the harness as a long-lived **bidirectional JSON-RPC** process.
- It manages multiple threads/sessions.
- A client request can produce many event updates.
- The server can initiate requests when agent input/approval is needed and pause until the client responds.

PEX plan:

- make Codex App Server the preferred adapter;
- consume thread events directly;
- map approval requests to PEX policy;
- send follow-up prompts through protocol rather than UI automation;
- track session/thread lifecycle;
- map Codex config/runtime information into the universal capability model;
- use repo/tests/filesystem as independent external evidence.

## 12.3 Claude Code — deep target

Current useful surfaces:

- Claude Agent SDK in Python/TypeScript.
- Rich hook lifecycle:
  - PreToolUse;
  - PostToolUse;
  - PostToolUseFailure;
  - UserPromptSubmit;
  - Stop;
  - SubagentStart/Stop;
  - PreCompact;
  - PermissionRequest;
  - SessionStart/End in supported SDK;
  - notifications and additional newer lifecycle events.
- Hooks can block/modify tool behavior, inject context, and implement custom approval flows.
- Agent hooks can independently inspect state before deciding if Claude may stop.

PEX plan:

- install PEX hook bundle globally/project-locally;
- forward events to bridge;
- use `UserPromptSubmit` for intent-lint/context enrichment;
- `PermissionRequest` for policy approvals;
- `Stop` for acceptance check/continuation;
- `PreCompact` for context checkpoint;
- optionally use Agent SDK for sessions started by PEX, but must still support user-started Claude sessions through hooks.

## 12.4 OpenCode — deep target

Current surface is excellent:

- `opencode serve` provides a headless HTTP server.
- OpenAPI specification.
- SSE event streams.
- Session list/create/status/get/delete/update/children/todos.
- session fork/abort/share/diff/summarize/revert.
- permission response endpoint.
- message read/write and async prompting.
- config read/patch.
- provider/model information.
- dynamic MCP.
- TUI prompt and control endpoints.
- plugins/events expose tool, permission, file, message, session lifecycle.

PEX plan:

- native HTTP/SSE adapter;
- use async prompt endpoint for nudges;
- permission endpoint for approval broker;
- fork for speculative execution/context refresh;
- diff/todo/status for verification and progress;
- config patch/MCP for JIT overlays;
- event stream for trajectory model.

## 12.5 Devin

Current official API supports:

- create sessions;
- list/get session state;
- send messages to active sessions;
- session status information;
- organization v3 API and service-user authentication;
- knowledge/playbook/secret concepts.

PEX plan:

- use official v3 API where account level permits;
- watch running/suspended/error/completed state;
- send context and corrective messages;
- create/resume sessions where supported;
- use project/repo external evidence for verification;
- because tool-level telemetry may be less exposed than local harnesses, declare reduced observation granularity rather than invent it.

## 12.6 Grok Build

Current official surface:

- interactive TUI;
- headless mode with streaming JSON;
- **ACP**;
- hooks/plugins/skills/MCP;
- open-source harness;
- configurable models.

PEX plan:

- prefer ACP/headless structured output;
- write PEX hook/plugin if additional lifecycle data is needed;
- source-level inspect public harness when protocol detail is undocumented;
- dynamic overlay through hooks/config/plugin system;
- use as a high-capability integration.

## 12.7 Grok Bot

Treat separately from Grok Build.

Goal:

- observe running bots/tasks;
- notify/route;
- send additional instructions where official product integration allows;
- use browser/desktop accessibility only if official control interfaces are absent and terms permit.

Do not claim deep programmatic control until confirmed.

## 12.8 Pi

Pi is intentionally minimal but highly extensible.

PEX plan:

- build a Pi TypeScript extension/package;
- emit structured tool/session events to PEX bridge;
- expose a receive/control path through extension or embedded core;
- use tmux/PTY only when direct embedding is impractical;
- because Pi has no built-in permission popups by philosophy, PEX policy should operate through extension/tool interception rather than pretending to answer nonexistent prompts.

## 12.9 OMP / Oh My Pi

Current surface is very favorable:

- interactive;
- one-shot;
- Node SDK;
- typed session events;
- RPC mode;
- ACP;
- extensions;
- rich tooling.

PEX plan:

- prefer SDK or RPC/ACP;
- create OMP extension for event forwarding and overlays;
- use typed session events for telemetry;
- use permission route over ACP where applicable.

## 12.10 Hermes Agent

Current surface:

- plugin hooks;
- shell hooks;
- outbound webhooks;
- session/tool/LLM lifecycle;
- `pre_tool_call` can block;
- `pre_llm_call` can inject context;
- messaging gateway across many chat platforms.

PEX plan:

- native Hermes plugin;
- emit outbound signed events to bridge;
- use pre-LLM hook for context injection;
- pre-tool for policy;
- exploit Hermes gateway as an optional remote PEX channel, without coupling the product to Hermes.

## 12.11 Prime Agent

Target official/current Prime Agent runtime.

Plan:

- inspect current source and runtime architecture;
- exploit durable sessions, local multiprocess runtime, and any exposed extension/event interfaces;
- if inherited Pi-compatible extension surfaces remain, build an adapter there;
- otherwise wrap current public programmatic/session APIs.

## 12.12 ZCode

“ZCode” is ambiguous across public projects/products.

Target the user’s actual chosen ZCode harness.

Plan:

- identify exact product/version during development;
- prefer official agent/runtime APIs, goal/session state, hooks/plugins, or local runtime over unofficial extraction;
- do not redistribute proprietary runtime code without permission.

## 12.13 Kimi Code

Current official surface includes:

- interactive CLI;
- one-shot prompt mode;
- resume/sessions;
- local server/API documented;
- ACP;
- hooks;
- plugins;
- custom system prompt;
- tools enable/disable;
- subagents;
- scheduled tasks;
- context export.

PEX plan:

- use local server/API or ACP;
- hook lifecycle to bridge;
- dynamic system/tool overlays;
- session export only as fallback/context source.

## 12.14 DeepSeek Harness

“DeepSeek harness” must be resolved to the exact first-party or user-selected implementation before integration.

Plan:

- verify official repository/docs and license;
- use plugin/event/session APIs if present;
- if the chosen harness is open-source, implement a native extension rather than brittle scraping.

## 12.15 Qwen Code

Current surface is excellent:

- headless mode with structured output;
- session management;
- SDKs;
- experimental daemon HTTP/SSE via `qwen serve`;
- hooks;
- auto-memory/skills;
- MCP;
- subagents;
- computer use;
- persistent project-scoped JSONL sessions.

PEX plan:

- prefer daemon/SDK;
- use hooks and session events;
- use headless resume for corrective prompts if needed;
- integrate memory/context overlays carefully to avoid duplicating Qwen’s own memory.

## 12.16 Adapter support labels

Expose one of:

- **Deep**: structured event stream + messaging + approvals/control + config/context.
- **Strong**: structured state + messaging + some intervention.
- **Basic**: status/context/message but limited intervention.
- **Observe-only**: reliable monitoring but no control.
- **Experimental**: fallback automation, unstable vendor surface.
- **Unavailable**: current version cannot be safely/legally integrated.

This is better than lying with a “supported” checkbox.

---

# 13. SESSION DISCOVERY

PEX should discover active work automatically where possible.

Signals:

- running processes;
- known local sockets/ports;
- ACP endpoints;
- App Server processes;
- OpenCode/Qwen/Kimi servers;
- registered hook heartbeats;
- vendor APIs for cloud sessions;
- session files/databases;
- OS windows and titles as supplementary hints.

Discovery returns candidates; adapters confirm identity.

Avoid attaching one project’s goal to another merely because their CWD names are similar.

---

# 14. PERSISTENT INTENT LEDGER

This is a central feature, not a notes field.

## 14.1 Why

Individual prompts are lossy.

A user can accidentally:

- contradict an earlier requirement;
- omit a key constraint;
- phrase a temporary tactic as if it were the final goal;
- forget why a design choice was rejected;
- move context to a new agent without important history.

PEX maintains a durable intent representation.

## 14.2 Intent extraction

When the user attaches a goal, PEX extracts:

- objective;
- acceptance criteria;
- constraints;
- non-goals;
- preferences;
- evidence required for completion;
- current decisions;
- unresolved questions.

The user can edit the ledger directly.

## 14.3 Prompt linting

Before a new user prompt reaches an attached agent, PEX can compare it against the ledger.

Classify:

- consistent;
- likely refinement;
- possible contradiction;
- explicit override;
- dangerous ambiguity.

Examples:

> Persistent constraint: “Do not alter dataset preprocessing.”

User says:

> “Just normalize all data first.”

PEX:

> “This conflicts with the active no-preprocessing-change constraint. Did you mean normalize only the evaluation copy?”

Depending on policy, PEX:

- rewrites obvious accidental ambiguity;
- asks on consequential contradictions;
- records explicit overrides as new decisions.

## 14.4 Agent-output linting

The same ledger scores whether agent actions still serve the actual goal.

---

# 15. CONTEXT MESH

## 15.1 Principle

Context is a project resource, not a chat artifact.

## 15.2 Context ingestion

Sources:

- agent transcripts/events;
- code diffs;
- commands/output;
- test results;
- user decisions;
- benchmark outputs;
- project docs;
- Git history;
- issue descriptions;
- context handed manually by user.

## 15.3 Context selection

Never dump the entire global memory into every agent.

Create a `ContextBundle` based on:

- active goal;
- task phase;
- agent role;
- files being touched;
- recent failures;
- decisions;
- unresolved dependencies.

Bundle should contain:

- goal summary;
- acceptance criteria;
- critical decisions;
- relevant artifacts;
- direct evidence;
- recent progress;
- explicit next objective;
- what not to redo;
- links/paths to deep context.

## 15.4 Handoff

When moving work between harnesses:

1. checkpoint source session;
2. extract unresolved state;
3. validate summary against artifacts/events;
4. produce compact context bundle;
5. start or attach target session;
6. inject bundle;
7. require target to restate interpreted goal internally/structurally if useful;
8. monitor first actions for handoff failure.

This replaces manual “summarize for another agent.”

## 15.5 Context health

Track:

- token/context utilization where exposed;
- number of compactions;
- repeated forgotten facts;
- contradictions;
- repeated reads;
- stale decisions;
- summary depth;
- context-to-progress ratio.

If health degrades:

- checkpoint;
- compact;
- migrate to fresh session;
- change context policy;
- reduce irrelevant tools/context.

---

# 16. TRAJECTORY MONITORING AND PROGNOSIS

PEX should not only review the final output.

It watches the trajectory.

## 16.1 Deterministic signals

Examples:

- same command/error repeating;
- same file reread many times;
- no file/test/state change for N significant steps;
- repeated web searches with semantically similar queries;
- long idle after unfinished TODO;
- process launched but never monitored;
- downstream work starts before required input/data exists;
- untracked temporary files balloon;
- context repeatedly compacted;
- agent claims success while tests/process state disagree;
- branch/worktree lacks expected diff;
- unresolved TODO remains when agent stops;
- permission loop;
- tests never run despite acceptance criterion;
- file edited but related generated artifact not updated;
- expensive tool loop with no new evidence.

## 16.2 Semantic signals

A Strands reasoning step may evaluate:

- current actions vs persistent objective;
- whether recent work is likely to produce useful evidence;
- whether the agent has drifted into generic cleanup/refactoring;
- whether it is polishing non-critical work;
- whether a plan ignores a known dependency;
- whether reasoning is looping without information gain;
- whether an intervention would be more harmful than waiting.

## 16.3 Drift score

Illustrative:

```text
drift =
  w1 * goal_action_semantic_distance
+ w2 * unresolved_dependency_violation
+ w3 * repeated_low_information_actions
+ w4 * acceptance_criterion_neglect
+ w5 * stale_context_signals
- w6 * verified_recent_progress
```

Do not hardcode one universal threshold. Calibrate and learn by harness/model/project class.

## 16.4 Stagnation score

Use event diversity, artifact deltas, new test evidence, and repeated errors.

## 16.5 Premature-completion score

At stop:

- acceptance criteria;
- unresolved tasks;
- tests/build;
- changed files;
- service health;
- user-requested artifact existence;
- hidden benchmark evaluator in benchmark mode;
- known failures.

If criteria are not met and continuing is safe:

PEX sends an evidence-grounded follow-up instead of asking the user to type “continue.”

---

# 17. ANTI-SLOP / FALSE-CLAIM HANDLING

The point is not to insult the agent. The point is to detect claims unsupported by state.

Examples:

- “tests pass” but no test command was run;
- “deployment complete” but endpoint is unreachable;
- “dataset loaded” but file/path is absent;
- “evaluation done” but expected outputs are incomplete;
- “all TODOs addressed” but task list remains;
- “fixed” but reproduction still fails;
- “saved file” but no artifact exists.

Implementation:

1. extract claim;
2. determine what observable evidence would support it;
3. query state/tools;
4. mark:
   - verified;
   - plausible but unverified;
   - contradicted;
5. if contradicted, route exact evidence back to worker;
6. do not bother human unless repeated failure or real decision.

---

# 18. DEPENDENCY AND SEQUENCING GUARD

This is specifically meant to catch subtle workflow mistakes such as preparing a kernel/process before the data/artifact it requires is available.

Maintain lightweight task/dependency DAG inferred from:

- plan;
- acceptance criteria;
- commands;
- artifacts;
- agent todos;
- repository state.

Before a high-cost action, PEX can check:

- prerequisite artifacts exist;
- expected producer task completed;
- required environment is ready;
- destructive action is not invalidated by upcoming work.

This should remain practical, not turn into formal verification of every shell command.

---

# 19. JIT HARNESS COMPILER

## 19.1 Concept

PEX can temporarily reshape the harness around the work.

The unit is an **ephemeral overlay**, not permanent vandalism of user configuration.

Overlay can include:

- system/project instructions;
- rules;
- tools enabled/disabled;
- MCP servers;
- model;
- reasoning effort;
- context bundle;
- permission policy;
- test/verifier instructions;
- token/context budget;
- subagent policy;
- research vs implementation mode;
- sandbox/worktree policy.

## 19.2 Examples

### Research phase
- strong search/browser tools;
- read-only repo;
- higher reasoning;
- evidence/citation requirement;
- no implementation tools unless requested.

### Implementation phase
- repository tools;
- tests/LSP;
- fewer broad research tools;
- explicit acceptance criteria;
- bounded web search.

### Debug phase
- debugger/log tools;
- reproduction command pinned;
- preserve failing state;
- higher tool-result attention.

### Eval phase
- deterministic scripts;
- immutable benchmark config;
- no benchmark-answer leakage;
- results saved to structured path;
- completion gated on row count/checksums.

### Context degradation
- start fresh session;
- minimal curated bundle;
- retain decisions and unresolved state;
- lower repeated-history payload.

## 19.3 Overlay lifecycle

Every overlay:

- has ID;
- reason;
- exact diff;
- TTL/scope;
- applied timestamp;
- affected session;
- rollback path.

Persistent config changes require explicit promotion or a well-defined user policy.

---

# 20. PERSONAL AGENT FINGERPRINTS

PEX learns from actual supervised trajectories.

Examples:

- “Cursor + model X tends to over-research frontend tasks.”
- “Codex configuration Y is reliable but frequently stops before running integration tests.”
- “This agent’s productivity drops sharply after second compaction.”
- “Harness A asks approval for the same safe test command repeatedly.”
- “Model B performs better when web search is disabled during implementation.”
- “Model C needs a stronger acceptance checklist on repository migrations.”

## 20.1 Learning signals

- interventions;
- whether intervention helped;
- verified final success;
- tool repetition;
- time-to-first-edit;
- time-to-first-test;
- premature stop;
- user corrections;
- token use;
- context compaction;
- errors;
- task type.

## 20.2 Use

Fingerprints influence:

- adapter selection;
- overlay generation;
- early-warning thresholds;
- model/tool configuration;
- handoff decision;
- amount of supervision.

Do not overfit from one session.

Show confidence/sample count.

---

# 21. HUMAN ATTENTION BROKER

Every detected issue should flow through:

```text
Can PEX safely ignore it?
  ↓ no
Can PEX safely and reversibly fix it?
  ↓ no
Can PEX gather more evidence without interrupting?
  ↓ no
Does a configured policy authorize the action?
  ↓ no
Is it a genuine human judgment?
  ↓ yes
Escalate with the minimum sufficient context.
```

## 21.1 Escalation format

Bad:

> “Codex needs input.”

Good:

> “Codex found two schema options. A preserves compatibility but adds one migration; B is cleaner but breaks existing checkpoints. Your persistent goal prioritizes backward compatibility, so I recommend A. Approve A / choose B / open Codex.”

## 21.2 Attention metric

Track:

- human intervention count;
- human active seconds if measurable/consented;
- decision count;
- unnecessary alert rate;
- average PEX auto-resolution confidence;
- reversals of PEX actions.

---

# 22. APPROVAL BROKER

PEX may approve routine actions only under explicit policy.

Possible policy dimensions:

- command class;
- path;
- repository;
- network target;
- write vs read;
- destructive operation;
- secret access;
- deployment environment;
- cost threshold;
- external side effect.

Examples:

Automatically approve:

- test commands;
- lint;
- typecheck;
- reading project files;
- non-destructive local build.

Ask:

- deleting large paths;
- force pushing;
- production deployment;
- migrations;
- secret export;
- account/billing actions;
- public posting;
- spending above threshold.

Never let the cloud supervisor directly bypass local policy.

---

# 23. SPECULATIVE EXECUTION

Optional but high-value feature.

When two approaches are plausible and cheap to probe:

1. create isolated worktrees/branches/session forks;
2. send approach A to one worker/config;
3. approach B to another;
4. limit probe budget;
5. compare:
   - test progress;
   - code complexity;
   - failures;
   - dependency fit;
   - token/time cost;
6. continue winner;
7. dispose loser safely;
8. preserve useful findings.

Use only when expected value exceeds overhead.

This is “branch prediction for agent work,” not uncontrolled agent spawning.

---

# 24. AUTOMATIC CLEANUP

PEX should clean low-risk residue when an agent has genuinely moved on:

- abandoned temp files;
- expired scratch artifacts;
- stale child processes;
- disposable worktrees;
- benchmark sandboxes;
- caches created specifically for one task if safe.

Rules:

- never delete ambiguous user data;
- inspect ownership/provenance;
- prefer move-to-quarantine before permanent delete;
- cleanup actions recorded in intervention log.

---

# 25. INTER-AGENT MESSAGING

Expose PEX as:

- local HTTP API;
- WebSocket;
- MCP server;
- optional ACP-compatible or tool interface where useful.

Other agents can ask:

- `pex.get_goal`
- `pex.get_relevant_context`
- `pex.report_progress`
- `pex.request_decision`
- `pex.find_agent_with_context`
- `pex.handoff`
- `pex.verify_claim`
- `pex.get_project_state`

Agents should not directly mutate another agent’s session. They ask PEX to route.

---

# 26. STRANDS AGENTS DESIGN

The project must use Strands meaningfully, not as a cosmetic wrapper.

Recommended design:


## 26.0 Supervisor model providers (BYOK, login, local, custom)

The supervisor LLM is user-pluggable. Binding text:


This section is binding for both the core product spec and the build spec.

Two independent layers must never be collapsed:

1. **Worker harnesses** — the coding agents the human already runs (Cursor, Codex, Claude Code, …).
2. **PEX supervisor model** — the LLM that *is* PEX: observes events, reasons, proposes typed interventions.

A user may run Codex as the worker and Claude as PEX, or Cursor as the worker and a local Llama as PEX. PEX must not assume OpenCode Zen, Bedrock, or any one vendor. PEX must not ship a machine-specific default API key or a single-provider module as the product.

PEX never requires the user to migrate into a PEX-owned coding harness. The supervisor model is pluggable. The worker set is pluggable.

---

## Auth modes (all first-class)

| Mode | Meaning |
| --- | --- |
| `api_key` / BYOK | User pastes a key. Stored locally, never committed, never uploaded in specs or git. |
| `login` | Vendor session/OAuth/CLI login the user already has (ChatGPT, Claude, Grok, Gemini, OpenCode, Hermes, …). Reuse local credentials when the vendor documents it. Do not scrape passwords. |
| `local` | No cloud key. Ollama, llama.cpp, LM Studio, vLLM, OpenAI-compatible localhost. |
| `custom` | User supplies `base_url` + optional key + model id. Any OpenAI-compatible or Anthropic-compatible endpoint. |
| `bedrock` / `agentcore` | AWS signed requests. Appropriate for the hackathon deploy path, not the only path. |

If a login flow is not yet implemented for a vendor, the adapter must say so. It must not fake Deep/connected. BYOK and custom endpoint must work without waiting for every OAuth.

---

## Provider registry PEX must support

Built-in named providers (OpenAI-compatible unless noted). Users can add more without a code change via `custom`.

**Frontier / hosted**

- OpenAI — `https://api.openai.com/v1` — `OPENAI_API_KEY`; ChatGPT/Codex **login** when local auth exists
- OpenAI Azure — user endpoint — `AZURE_OPENAI_API_KEY`
- Anthropic — native Messages API — `ANTHROPIC_API_KEY`; Claude **login** when local auth exists
- Google Gemini — `GEMINI_API_KEY` / `GOOGLE_API_KEY`; Google **login** when available
- xAI Grok — `https://api.x.ai/v1` — `XAI_API_KEY`; Grok **login** when local auth exists
- Amazon Bedrock / AgentCore — AWS credentials / profile
- Mistral — `MISTRAL_API_KEY`
- Cohere — `COHERE_API_KEY`
- Groq — `https://api.groq.com/openai/v1` — `GROQ_API_KEY`
- Together — `https://api.together.xyz/v1` — `TOGETHER_API_KEY`
- Fireworks — `https://api.fireworks.ai/inference/v1` — `FIREWORKS_API_KEY`
- DeepSeek — `https://api.deepseek.com/v1` — `DEEPSEEK_API_KEY`
- Moonshot / Kimi — `https://api.moonshot.ai/v1` — `MOONSHOT_API_KEY`
- DashScope / Qwen — `DASHSCOPE_API_KEY`
- NVIDIA NIM / build.nvidia.com — `NVIDIA_API_KEY`
- Perplexity — `PERPLEXITY_API_KEY`
- Hugging Face Inference — `HF_TOKEN`
- GitHub Models — `GITHUB_TOKEN`
- OpenRouter — `https://openrouter.ai/api/v1` — `OPENROUTER_API_KEY` (one key, many models)
- OpenCode Zen — `https://opencode.ai/zen/v1` — `OPENCODE_API_KEY` / `PEX_ZEN_API_KEY`
- OpenCode Go — `https://opencode.ai/zen/go/v1` — Go key
- Hermes / Nous — `HERMES_API_KEY` / `NOUS_API_KEY` + documented Nous/Hermes base URL
- Writer — Strands `WriterModel` when configured
- SageMaker — Strands `SageMakerAIModel` when configured
- Llama API — Strands `LlamaAPIModel` when configured

**Local / open-source runtimes**

- Ollama — `http://127.0.0.1:11434`
- LM Studio — `http://127.0.0.1:1234/v1`
- llama.cpp server — user port
- vLLM / SGLang / TGI — user endpoint
- Any other OpenAI-compatible local server

**Escape hatch**

- `custom`: `PEX_SUPERVISOR_BASE_URL` + `PEX_SUPERVISOR_API_KEY` + `PEX_SUPERVISOR_MODEL`
- `litellm`: optional Strands LiteLLM backend for additional vendors without a first-class entry

LiteLLM and OpenRouter are how PEX reaches providers not listed above without pretending we first-partied them.

---

## Configuration (no machine-specific defaults)

```text
PEX_SUPERVISOR_PROVIDER=openai|anthropic|google|grok|openrouter|zen|opencode_go|bedrock|ollama|lmstudio|llamacpp|vllm|groq|together|fireworks|deepseek|moonshot|mistral|cohere|hermes|huggingface|azure_openai|github_models|nvidia|perplexity|dashscope|custom|litellm
PEX_SUPERVISOR_MODEL=<provider model id>
PEX_SUPERVISOR_API_KEY=<optional; else provider-specific env>
PEX_SUPERVISOR_BASE_URL=<optional override or custom endpoint>
PEX_SUPERVISOR_AUTH=api_key|login|local|custom
```

Keys live in the user’s environment, OS secret store, or local `.env` (gitignored). **Never** commit keys. **Never** bake a developer’s Zen/OpenAI/Anthropic key into the repo, specs on GitHub, or a `zen.py`-only product path.

If nothing is configured, PEX stays on deterministic triage and reports `used_llm=false` honestly.

Auto-detect order when `PEX_SUPERVISOR_PROVIDER` is unset: explicit custom base URL, then the first configured key among the registry, then local Ollama/LM Studio if a server responds. Auto-detect must be logged. It must not silently prefer the original author’s laptop.

---

## Web search for verification (BYOK, official endpoints)

When PEX must check a worker claim against the public web, it uses documented search/scrape APIs. This is verification, not a hidden evaluator. Keys are BYOK. Never used to read `evaluator.py`, `metadata.yaml`, or planted oracles.

| Backend | Endpoint | Auth |
| --- | --- | --- |
| Firecrawl search | `POST https://api.firecrawl.dev/v2/search` | `Authorization: Bearer $FIRECRAWL_API_KEY` |
| Firecrawl scrape | `POST https://api.firecrawl.dev/v2/scrape` | `Authorization: Bearer $FIRECRAWL_API_KEY` |
| Exa | `POST https://api.exa.ai/search` | `x-api-key` or `Authorization: Bearer $EXA_API_KEY` |
| Tavily | `POST https://api.tavily.com/search` | `api_key` in JSON body |
| Brave | `GET https://api.search.brave.com/res/v1/web/search` | `X-Subscription-Token` |
| Serper | `POST https://google.serper.dev/search` | `X-API-KEY` |
| DuckDuckGo Instant Answer | `GET https://api.duckduckgo.com/` | none (last resort; not a full web index) |

Supervisor tools: `web_search`, `scrape_url`. Prefer Firecrawl/Exa when keys exist.

---

## Catalog: at least the current top models

PEX ships a **catalog**, not a hardwired brain. IDs change; refresh from each vendor’s `/models` (OpenRouter `GET https://openrouter.ai/api/v1/models`, Zen `GET https://opencode.ai/zen/v1/models`, Ollama `/api/tags`). The following is the starting top set the product must be able to select as the PEX supervisor (and, separately, that users may point a worker at). It is not a claim that every ID is live forever.

**OpenAI:** gpt-5.6-sol, gpt-5.6-terra, gpt-5.6-luna, gpt-5.5, gpt-5.5-pro, gpt-5.4, gpt-5.4-pro, gpt-5.4-mini, gpt-5.4-nano, gpt-5.3-codex, gpt-5.2, gpt-5.1, gpt-5, gpt-5-nano

**Anthropic:** claude-fable-5, claude-opus-5, claude-sonnet-5, claude-opus-4.8, claude-opus-4.7, claude-sonnet-4.6, claude-sonnet-4.5, claude-haiku-4.5

**Google:** gemini-3.1-pro, gemini-3.7-flash, gemini-3.6-flash, gemini-3.5-flash, gemini-3-flash

**xAI:** grok-4.6, grok-4.5, grok-build-0.1

**Open / open-weight (hosted or local):** Llama 4, Qwen3.x, DeepSeek V4 Pro/Flash, Kimi K3 / K2.7 Code, GLM-5.x, MiniMax M3/M2.7, Mistral family, Nemotron, MiMo, Hy3, Ox Alpha / Zen free previews, Muse Spark, Big Pickle

**Gateways:** any OpenRouter slug (`openai/…`, `anthropic/…`, `x-ai/…`, `meta-llama/…`, `qwen/…`, `deepseek/…`, stealth models)

That set is **more than 50** selectable supervisor models once provider × ID is counted. The UI should show the catalog plus “paste any model id”.

---

## Worker harnesses (unchanged product surface)

Supervisor-model choice does **not** replace harness adapters. PEX still attaches to the user’s agents:

Cursor, OpenAI Codex, Claude Code, OpenCode, Devin, Grok Build, Grok Bot (observe until an official control API exists), Pi, OMP / Oh My Pi, Hermes Agent, Prime Agent, ZCode, Kimi Code, DeepSeek harness, Qwen Code.

Deepest control first: official API → ACP → hooks → headless → local session data. Do not fake identical control. Cursor and Codex remain the first deep benchmark targets.

---

## Implementation rules

- Use Strands `Model` implementations when they exist (OpenAI, OpenAI Responses, Anthropic, Gemini, Bedrock, Ollama, llama.cpp, Mistral, LiteLLM, Writer, SageMaker, Llama API).
- Use OpenAI-compatible `base_url` for everyone else, including Zen, OpenRouter, Groq, Together, Fireworks, DeepSeek, xAI, LM Studio, vLLM, custom.
- Record `provider`, `model_id`, `base_url` (no secrets), `auth_mode`, `inference_request_id` on every PEX inference.
- Adding a provider = registry row + env names + catalog ids. Not a fork of the supervisor loop.

## 26.1 Main Supervisor Agent

Responsibilities:

- interpret normalized events;
- reason over persistent goal;
- decide whether intervention is needed;
- select typed action;
- explain concise rationale;
- defer deterministic checks to tools.

Tools:

- `get_goal`
- `get_context`
- `get_session_state`
- `get_recent_events`
- `get_diff`
- `run_verification`
- `send_harness_message`
- `request_context_handoff`
- `propose_overlay`
- `apply_allowed_overlay`
- `respond_permission`
- `ask_human`
- `record_intervention`
- `query_fingerprint`
- `update_fingerprint`

## 26.2 Independent Verifier Agent

Used only when semantic verification is required.

It should not inherit the worker’s confident narrative blindly.

Input should emphasize:

- goal;
- observable state;
- artifacts;
- tests;
- claims.

Output structured verdict.

## 26.3 Harness Optimizer

On-demand component:

- diagnoses token waste/context/tool mismatch;
- proposes ephemeral overlay;
- uses fingerprint/history;
- must justify expected benefit.

## 26.4 Context Packager

On-demand component:

- creates minimal handoff bundle;
- preserves provenance;
- avoids irrelevant transcript dumping.

## 26.5 Strands Graph

Use a graph/workflow where it genuinely clarifies a high-stakes intervention:

```text
Event
  → deterministic triage
  → goal relevance
  → trajectory assessment
  → need intervention?
      no → record
      yes
        → risk/policy
        → gather evidence
        → propose action
        → local policy check
        → execute or ask human
        → observe outcome
        → update fingerprint
```

Avoid “seven agents debating each other” merely to impress judges.

---

# 27. AGENTCORE / AWS DESIGN

Use AgentCore because the rules explicitly say it can strengthen Technical Implementation.

Recommended:

## 27.1 AgentCore Runtime
Deploy Strands supervisor service.

## 27.2 AgentCore Memory
Store appropriate long-term semantic/summarized state such as:

- user supervision preferences;
- durable project facts;
- agent fingerprints;
- recurring policies;
- decision summaries.

Do not blindly upload secrets/raw repositories.

## 27.3 Observability
Use AgentCore/CloudWatch tracing and metrics.

Record:

- supervisor invocation;
- event classification;
- tool/action chosen;
- latency;
- token/cost if available;
- intervention outcome;
- failure.

Make a sanitized trace screenshot/view useful in the hackathon presentation.

## 27.4 Identity/security
Use AWS identity mechanisms appropriately for cloud resources.

Local harness credentials remain local whenever possible.

## 27.5 Optional services
Use only when they add real value:

- AgentCore Code Interpreter for benchmark/stat analysis or safe computation;
- AgentCore Browser only if a real browser task is part of the product;
- Gateway/MCP only if it simplifies a genuine integration.

Do not add AWS services as decorative architecture confetti.

---

# 28. LOCAL BRIDGE

Recommended Python service because Strands and many integrations are Python-friendly.

Responsibilities:

- adapter lifecycle;
- session discovery;
- event normalization;
- local SQLite;
- filesystem/process watchers;
- local policy enforcement;
- secret redaction;
- request batching;
- connectivity to AgentCore;
- action execution;
- UI websocket;
- benchmark instrumentation.

Recommended framework:

- FastAPI or a lighter async server;
- WebSocket for UI;
- Unix domain socket/local named pipe where practical for trusted local communication;
- authenticated localhost HTTP only where integrations require it.

---

# 29. EVENT PIPELINE

High-frequency raw events should not all invoke a frontier model.

Pipeline:

1. raw vendor event;
2. normalize;
3. deterministic feature extraction;
4. cheap rule/state filters;
5. batch/coalesce;
6. semantic supervisor only if event may matter;
7. typed intervention;
8. local policy;
9. execute;
10. observe outcome.

Example:

50 consecutive token deltas should become one semantic update, not 50 cloud calls.

---

# 30. INTERVENTION TYPES

Typed enum:

```text
NOOP
ANNOTATE
NOTIFY
SEND_NUDGE
INJECT_CONTEXT
CONTINUE_SESSION
REQUEST_VERIFICATION
RESPOND_PERMISSION
APPLY_OVERLAY
REVERT_OVERLAY
FRESH_HANDOFF
START_AGENT
STOP_AGENT
FORK_PROBE
CLEANUP
FOCUS_UI
ASK_HUMAN
```

Every action has:

- confidence;
- evidence;
- risk;
- reversibility;
- expected benefit;
- cooldown.

Prevent intervention storms.

---

# 31. TOKEN / COST OPTIMIZATION

PEX must account for its own overhead.

Signals:

- repeated identical file reads;
- repeated searches;
- low information gain;
- overly broad context;
- frequent compaction;
- high reasoning model on trivial step;
- agent re-deriving known context;
- multiple workers duplicating same investigation;
- too many installed MCP/tool descriptions;
- unnecessary system prompt bloat.

Actions:

- inject known answer/context;
- disable irrelevant tools;
- route to cheaper model if harness supports and quality risk is low;
- reduce context;
- start fresh session;
- stop duplicate investigation;
- share result from another agent.

Metric:

> total tokens/cost per verified successful task

Not merely raw token reduction.

---

# 32. SECURITY AND PRIVACY

This product watches powerful local agents. Treat it as privileged software.

## 32.1 Threat model

Risks:

- prompt injection in repo/web content tries to control PEX;
- malicious agent message asks PEX for higher authority;
- secrets in transcripts;
- cloud exfiltration;
- destructive approvals;
- wrong-session context injection;
- compromised adapter/plugin;
- remote chat impersonation;
- stale policy;
- PEX supervisor hallucinated action.

## 32.2 Required mitigations

- typed actions, never arbitrary shell text from cloud supervisor unless explicitly passed through a safe execution layer;
- local allow/deny policy;
- project/session identity binding;
- secret redaction before cloud;
- optional local-only fields;
- authentication for local control APIs;
- signed/verified remote callbacks where relevant;
- full intervention audit trail;
- minimum privilege;
- irreversible/high-risk actions require human or explicit policy;
- do not expose raw hidden credentials to the model;
- capability negotiation;
- replay protection for permission decisions;
- rate limits/cooldowns.

## 32.3 Prompt injection boundary

Treat tool/web/repository content as untrusted data.

Only the persistent human intent/policy can authorize new privileges.

---

# 33. TEST STRATEGY

Testing is a first-class product feature.

## 33.1 Unit tests

Test:

- event normalization;
- goal diff;
- intent contradiction classification helpers;
- context selection;
- policy engine;
- risk scoring;
- cooldowns;
- overlay diff/revert;
- drift features;
- stagnation features;
- claim/evidence mapping;
- adapter capability negotiation;
- benchmark statistics.

## 33.2 Contract tests

Every adapter passes a shared suite:

- discovery returns stable identity;
- events normalize;
- send message reaches correct session;
- permission response maps correctly if supported;
- stop/resume semantics;
- context injection;
- no cross-session leakage;
- disconnect/reconnect;
- vendor update failure surfaces clearly.

## 33.3 Adapter integration tests

Use real harnesses where feasible.

Record sanitized fixtures for deterministic CI but do not replace live smoke tests.

## 33.4 End-to-end tests

Scenarios:

1. Start Cursor task → PEX attaches → detects premature stop → sends evidence → task completes.
2. Start Codex task → approval requested → PEX policy auto-approves safe test → continues.
3. Context from Codex needed by Cursor → PEX creates bundle → Cursor receives it.
4. User prompt contradicts goal → PEX catches before delivery.
5. Agent loops on same error → PEX diagnoses stagnation and redirects.
6. Agent claims test pass → state contradicts → PEX reopens work.
7. Context degrades → PEX starts fresh session and hands off.
8. Network to AgentCore drops → local bridge degrades safely, does not approve dangerous action.
9. Wrong adapter emits malformed event → does not crash all supervision.
10. User pauses PEX → no interventions occur.

## 33.5 Chaos tests

Inject:

- duplicate events;
- reordered events;
- lost events;
- vendor process restart;
- stale session ID;
- bridge restart;
- cloud timeout;
- malformed tool result;
- huge transcript;
- permission storm;
- multiple sessions same repo;
- agent changes branch unexpectedly.

## 33.6 UX tests

The pet must not become annoying.

Measure:

- number of visible notifications;
- average time to identify which agent needs attention;
- accidental click obstruction;
- CPU/memory;
- animation smoothness;
- always-on-top behavior;
- multiple monitors;
- Linux/Windows/macOS where feasible.

---

# 34. BENCHMARK: PRIMARY EXPERIMENT

This benchmark is central to the product and the impact claim.

## 34.1 Research question

Does PEX improve coding-agent task success and reduce human-management burden when supervising real harnesses?

## 34.2 Four arms

For every benchmark task:

1. Cursor baseline
2. Cursor + PEX
3. Codex baseline
4. Codex + PEX

## 34.3 Experimental principle

The important comparison is **within harness**:

- Cursor+PEX vs Cursor baseline
- Codex+PEX vs Codex baseline

Do not claim direct Cursor-vs-Codex superiority unless model/settings are truly comparable.

## 34.4 Control variables

Within each harness:

- same model;
- same model version where controllable;
- same reasoning effort;
- same initial user prompt;
- same repository commit;
- same network policy;
- same tools except PEX-required integration surface;
- same environment;
- fresh worktree/container;
- fresh session;
- same time/budget policy.

Randomize order to reduce time/vendor drift effects.

Record exact versions.

## 34.5 Benchmark size

Development smoke:

- 8–10 tasks.

Intermediate:

- ~20 tasks.

Final target:

- **30+ paired tasks** if cost/time permits.

Do not lower the final count merely to obtain prettier results.

If more tasks are affordable, increase them.

## 34.6 Task sources

Use two complementary sets.

### A. Natural coding tasks
Examples:

- fixed subset of public reproducible repo issues;
- SWE-bench Verified-compatible tasks where harness execution setup is practical;
- other open-source bug/feature tasks with objective tests.

### B. PEX management-stress tasks
Create a public benchmark suite, working name **PexBench**, where the coding task is real but the workflow includes a management stressor.

Categories:

1. premature stop;
2. forgotten acceptance criterion;
3. dependency ordering;
4. context loss/compaction;
5. repeated error loop;
6. unnecessary research/tool loop;
7. permission interruption;
8. cross-session handoff;
9. user prompt contradiction;
10. false completion claim;
11. long-running process not monitored;
12. duplicate work across agents.

Never give PEX oracle access to hidden answer data.

## 34.7 Hidden evaluation

Agent and PEX should not see hidden evaluator expectations beyond normal task requirements.

Evaluator may run:

- hidden tests;
- static assertions;
- service probes;
- artifact existence;
- correctness scripts.

## 34.8 Primary metric

### Task Success Rate

Binary success by independent objective evaluator.

Report:

- Cursor baseline success %
- Cursor+PEX success %
- absolute percentage-point lift
- relative lift
- uncertainty

Same for Codex.

## 34.9 Secondary metrics

- human interventions/task;
- human interventions/successful task;
- human active management time;
- wall-clock completion time;
- total agent tokens;
- PEX supervisor tokens;
- total combined tokens;
- estimated combined monetary cost;
- number of tool calls;
- repeated tool-call rate;
- context resets;
- premature-stop count;
- false-done count;
- PEX interventions;
- PEX interventions judged helpful;
- harmful PEX interventions;
- alerts shown to human;
- approvals auto-handled;
- cross-agent context handoffs;
- successful task per dollar;
- successful task per human intervention.

The headline secondary metric should be:

> **human interventions per successful task**

## 34.10 Two budget regimes if feasible

### Natural completion
Let each arm operate under the same generous max wall-clock cutoff and report natural total cost.

### Budget-matched
Set comparable total resource caps including PEX overhead.

This prevents the criticism that success improved only because PEX spent unlimited extra model calls.

## 34.11 Statistical analysis

For paired binary success:

- McNemar test where assumptions apply;
- paired bootstrap confidence interval for absolute success lift;
- Wilson intervals for individual success proportions.

For continuous paired metrics:

- paired bootstrap;
- Wilcoxon signed-rank or appropriate paired test;
- show median and distribution, not only mean.

Report raw N and failures.

Do not worship p-values with tiny N.

## 34.12 Benchmark integrity

- freeze final benchmark task list before final optimization;
- maintain separate development tasks;
- no task-specific hardcoded PEX rules;
- no manually rescuing treatment arms unless that exact human action is counted;
- human interventions must be logged;
- raw event/result logs immutable;
- record aborted runs and why;
- no selective reruns without a predefined rerun policy;
- disclose vendor outages;
- pin software versions where possible.

---

# 35. PEXBENCH DESIGN

Each task package:

```text
task/
├─ metadata.yaml
├─ repo/
├─ setup.sh
├─ prompt.md
├─ stressor.yaml
├─ public_tests.sh
├─ hidden_evaluator/
└─ expected_artifacts.yaml
```

Example stressor:

```yaml
type: dependency_order
trigger:
  when_agent_attempts:
    - "launch training"
  while_missing:
    - "prepared_dataset"
expected_supervisor_behavior:
  - detect prerequisite missing
  - redirect agent before expensive run
forbidden:
  - reveal hidden solution
```

Stressor injection should mimic genuine agent-management failure, not sabotage arbitrarily.

---

# 36. PROGRESS MEASUREMENT

Define “verified progress events”:

- failing reproduction established;
- test added;
- failing test changes to pass;
- relevant diff created;
- dependency resolved;
- benchmark rows produced;
- service endpoint becomes healthy;
- artifact checksum appears;
- acceptance criterion verified.

Use this to estimate:

```text
progress_efficiency =
verified_progress_events / normalized_resource_cost
```

This can help detect spinning.

---

# 37. OBSERVABILITY

Every normalized event should be queryable.

Minimum:

- event timeline;
- session timeline;
- interventions;
- action result;
- supervisor latency;
- adapter errors;
- policy decisions;
- cost/tokens;
- benchmark IDs.

Provide a “why did PEX do that?” path in UI.

No mysterious autonomous behavior.

---

# 38. PERFORMANCE TARGETS

These are targets, not excuses to cut capabilities.

- Local passive observation should be low CPU.
- Pet UI should feel immediate.
- Deterministic event processing: near-real-time.
- Semantic intervention latency should not block unrelated harness work.
- High-frequency events must be batched.
- Cloud outage should not freeze local harnesses.
- Pet crash should not kill bridge.
- Adapter crash should not kill other adapters.

---

# 39. DEVELOPMENT MILESTONES

Milestones are ordering, not a scope cap.

## M0 — Foundation

- repo;
- protocol schemas;
- local bridge;
- event bus;
- SQLite;
- minimal pet;
- Strands hello path;
- AgentCore deployment proof;
- test framework.

Acceptance:

- pet sees bridge;
- one synthetic session emits events;
- Strands supervisor receives normalized event;
- action round trip works through policy.

## M1 — Cursor deep adapter

- hook install;
- event stream;
- transcript/context;
- prompt interception;
- stop interception;
- message/control via ACP/CLI;
- permission behavior where exposed.

Acceptance:

- real Cursor session visible;
- PEX can nudge;
- PEX catches unfinished stop;
- UI jumps to session;
- contract tests pass.

## M2 — Codex deep adapter

- App Server;
- thread discovery;
- events;
- approval requests;
- follow-ups;
- state.

Acceptance:

- real Codex session controlled without screen scraping;
- permission broker demo;
- contract tests.

## M3 — Intent + Context

- Goal editor;
- ledger;
- context items;
- handoff bundle;
- user prompt contradiction.

Acceptance:

- Codex → Cursor context handoff succeeds;
- no manual copy/paste;
- contradictory prompt produces correct PEX behavior.

## M4 — Supervisor intelligence

- drift/stagnation;
- premature completion;
- claim verification;
- dependency guard;
- intervention outcome tracking.

Acceptance:

- scripted stress scenarios pass.

## M5 — JIT Harness Compiler

- overlay schema;
- Cursor/Codex overlays;
- reversible apply/revert;
- rationale;
- context health handling.

## M6 — Additional harnesses

Deep/strong adapters in priority order based on exposed APIs:

- OpenCode;
- Claude Code;
- Grok Build;
- OMP;
- Qwen Code;
- Kimi Code;
- Hermes;
- Devin;
- Pi;
- Prime Agent;
- remaining target integrations.

Continue until the full target list has the strongest practical adapter.

## M7 — Remote and polish

- Telegram/Discord;
- pet animation/state;
- command deck;
- onboarding;
- installer;
- permissions;
- recovery.

## M8 — Benchmark

- freeze PexBench;
- run smoke;
- debug benchmark infrastructure;
- freeze final policies;
- run final four-arm experiment;
- analyze raw data;
- generate plots/tables.

## M9 — Hackathon submission

- public repo;
- license;
- README;
- architecture diagram;
- live demo;
- 5-minute video;
- Devpost text;
- builder.aws posts;
- reproducibility instructions.

---

# 40. “DO NOT REGRESS” ACCEPTANCE BAR

Before any major merge:

- all unit tests pass;
- adapter contract tests pass for affected adapters;
- no existing deep integration loses capability silently;
- baseline benchmark runner still executes;
- PEX treatment runner still executes;
- UI can load without cloud;
- risky action policy still enforced;
- overlay rollback works;
- audit log preserved.

Do not replace a difficult native adapter with screen automation unless the native interface truly ceased to exist.

---

# 41. PRODUCT QUALITY BAR

Final submission should feel like something a power user would leave running.

Required:

- installable;
- recoverable after restart;
- useful errors;
- no hardcoded local paths;
- secure credential storage;
- versioned configs;
- clean first-run onboarding;
- adapter health screen;
- clear degraded modes;
- polished pet behavior;
- no terminal full of unexplained debug spam;
- robust reconnect;
- docs for adding adapters.

---

# 42. DEMO STORYBOARD — MAX 5 MINUTES

The demo should show PEX solving management work, not merely show architecture.

## 0:00–0:25 — Hook

Show desktop with Cursor + Codex + another agent running.

Narration:

> “AI agents save me coding time, then quietly created a new job: managing the agents. I spend my day carrying context, checking whether ‘done’ is actually done, approving repetitive actions, and telling long-running agents not to wander off.”

Pet shows:

`3 working · 0 need you`

## 0:25–1:05 — Premature completion / false claim

Codex claims a task is done.

PEX checks acceptance state.

A required test/artifact is missing.

Pet:

`Codex stopped early · continuing`

PEX sends exact evidence.

Codex resumes.

No human action.

## 1:05–1:45 — Cross-harness context

Cursor needs knowledge discovered in Codex.

PEX notices relevance.

Pet:

`Shared 3 relevant facts → Cursor`

Show context bundle, not whole transcript.

Cursor immediately proceeds.

## 1:45–2:20 — Permission/attention

Cursor requests routine test permission.

PEX policy approves.

Then a consequential migration decision appears.

PEX does not decide silently.

Pet:

`Decision needed`

Click.

Show concise tradeoff and recommendation.

## 2:20–2:55 — JIT harness adaptation

PEX detects a session wasting context/tokens or entering a new phase.

Show overlay:

- disables irrelevant tools;
- injects acceptance criteria;
- changes reasoning/tool policy;
- or fresh-handoffs degraded session.

## 2:55–3:30 — Ask PEX

Ask:

> “What needs me?”

PEX answers without interrupting workers.

## 3:30–4:15 — Benchmark evidence

Show four-arm result.

Example visualization structure:

```text
Task success
Cursor        baseline XX% → +PEX YY%
Codex         baseline XX% → +PEX YY%

Human interventions / successful task
Cursor        A → B
Codex         C → D
```

Use real results only.

## 4:15–4:45 — Architecture

One clean diagram:

existing harnesses → local bridge → Strands/AgentCore supervisor → policy → interventions → pet.

Mention:

- Strands;
- AgentCore Runtime;
- Memory;
- Observability;
- vendor adapters.

## 4:45–5:00 — Close

> “PEX doesn’t replace your agents. It removes the new layer of work created by having them. You keep the goals and the decisions. PEX handles the babysitting.”

---

# 43. HACKATHON BLOG STRATEGY

If Stage Two rules still support +0.6, publish three genuinely useful posts.

Possible topics:

1. **Agents for Humans: Building a Cross-Harness Supervisor with Strands and AgentCore**
2. **Agents for Humans: Measuring Human Attention as an Agent Benchmark**
3. **Agents for Humans: Designing Safe Autonomous Approvals Across Coding Agents**

Each should include real implementation lessons, not filler.

Reconfirm current rule wording before publication.

---

# 44. ARCHITECTURE DIAGRAM CONTENT

Official FAQ asks for a diagram showing:

- user input/interface;
- Strands agent loop;
- tools/integrations;
- AWS services;
- output.

PEX diagram should visibly label:

- human;
- PEX pet;
- local bridge;
- adapter layer;
- Cursor/Codex/etc.;
- Strands Supervisor;
- AgentCore Runtime;
- AgentCore Memory;
- observability/CloudWatch;
- policy enforcement;
- context store;
- output/interventions.

---

# 45. PUBLIC README MUST ANSWER

In first screenful:

1. What is PEX?
2. What pain does it remove?
3. GIF/video.
4. Supported harness matrix.
5. Why it is not another orchestrator.
6. Benchmark headline.
7. Quick install.
8. Architecture.

Then:

- setup;
- AWS config;
- privacy;
- adapter development;
- benchmark reproduction;
- license;
- hackathon disclosure.

---

# 46. LIVE DEMO STRATEGY

Because judges may not install 15 paid coding products:

Provide a live/safe mode that demonstrates:

- pet;
- event timelines;
- recorded sanitized real trajectories;
- Strands reasoning;
- context mesh;
- benchmark explorer.

But the video must also show **real live integrations** with at least Cursor and Codex.

Do not misrepresent replay as live control.

---

# 47. FAILURE MODES TO DESIGN AGAINST

1. PEX nags more than humans previously intervened.
2. PEX sends too much context and makes agents worse.
3. PEX corrects a productive unconventional trajectory.
4. PEX approves a dangerous command.
5. PEX responds to the wrong session.
6. Vendor updates event schema.
7. AgentCore unreachable.
8. PEX semantic judge is fooled by agent narration.
9. PEX’s own token cost erases benefit.
10. Fingerprint overfits one bad run.
11. Context mesh stores stale decision.
12. User explicitly changes goal but PEX keeps old goal.
13. Two goals share repo but not objective.
14. Multiple agents edit same files simultaneously.
15. Pet UI becomes distracting.
16. Remote message contains sensitive content.
17. Benchmark PEX knows hidden evaluator.
18. PEX creates intervention loop: nudge → agent responds → PEX re-nudges.
19. PEX fresh-handoff loses an unrecorded decision.
20. Cleanup deletes useful scratch work.

Every one should have mitigation/tests.

---

# 48. EVALUATION OF PEX ITSELF

PEX needs its own supervisor-quality metrics.

For labeled dev trajectories:

- intervention precision:
  - fraction of interventions that were actually useful;
- intervention recall:
  - fraction of important management failures caught;
- harmful intervention rate;
- false alert rate;
- decision escalation precision;
- context handoff sufficiency;
- context handoff compression ratio;
- premature-stop detection;
- false-claim detection;
- approval-policy accuracy;
- overlay benefit.

A product that improves task success but annoys the user every minute is not successful.

---

# 49. TEST FIXTURES FOR “LITTLE UNNOTICEABLE SLOP”

Create realistic cases.

Examples:

### Fixture: missing data prerequisite
Goal requires evaluation on generated dataset.

Worker starts expensive evaluator before dataset generation completed.

PEX should detect missing prerequisite and redirect.

### Fixture: stale command
Worker repeatedly reruns test command whose failure is caused by an unchanged config.

PEX should identify repeated identical failure and demand/change diagnosis.

### Fixture: premature cleanup
Worker deletes intermediate artifacts still needed by another active task.

PEX should block/ask.

### Fixture: generic refactor drift
Worker starts broad refactor unrelated to acceptance criteria.

PEX should nudge back unless refactor is necessary.

### Fixture: silent missing benchmark rows
Worker reports benchmark done but output has 27/30 rows.

PEX should reopen.

### Fixture: abandoned background process
Worker launches server/train/eval then stops monitoring it.

PEX should monitor state and wake/re-prompt.

### Fixture: user contradiction
User says “switch to X” despite durable decision “X was rejected because Y.”

PEX should surface conflict.

---

# 50. CONTEXT SHARING ALGORITHM

A simple first implementation:

1. Extract candidate context items from source session.
2. Score each item:

```text
score =
  goal_relevance
+ target_task_relevance
+ unresolved_dependency_value
+ recency
+ decision_importance
+ evidence_strength
- redundancy
- staleness
- sensitivity_penalty
```

3. Select under token budget.
4. Include pointers to artifacts rather than full contents when target can read them.
5. Add “do not redo” section for completed investigations.
6. Validate bundle against current source state.
7. Record what was shared.

Later improve with learned retrieval.

---

# 51. INTERVENTION OUTCOME LEARNING

After each intervention, determine whether it helped.

Possible signals:

- agent exits repeated loop;
- new verified progress;
- failure resolved;
- unnecessary branch abandoned;
- task succeeds;
- user reverses PEX;
- agent becomes more confused;
- token burn increases without progress.

Update fingerprint only with uncertainty and minimum sample logic.

---

# 52. SAFE AUTONOMY LEVELS

User-adjustable:

### Observe
No actions.

### Assist
Notify and prepare suggested messages.

### Nudge
Can send low-risk corrective prompts/context.

### Manage
Can continue sessions, perform handoffs, apply reversible overlays, handle routine approvals.

### Autopilot
Can manage within explicit policy and ask only real decisions.

Per-project overrides.

The demo can use Manage/Autopilot in a sandboxed project.

---

# 53. PEX API SKETCH

```http
GET  /v1/sessions
GET  /v1/sessions/{id}
GET  /v1/goals/{id}
POST /v1/goals
PATCH /v1/goals/{id}

POST /v1/sessions/{id}/attach
POST /v1/sessions/{id}/message
POST /v1/sessions/{id}/pause-supervision
POST /v1/sessions/{id}/resume-supervision
POST /v1/sessions/{id}/handoff
POST /v1/sessions/{id}/verify

GET  /v1/context/search
GET  /v1/interventions
POST /v1/decisions/{id}/resolve

GET  /v1/adapters
GET  /v1/adapters/{name}/health

GET  /v1/bench/runs
```

WebSocket:

`/v1/events`

MCP tools mirror safe high-level operations.

---

# 54. CONFIG EXAMPLE

```yaml
pex:
  autonomy: manage
  cloud_reasoning: true
  telemetry: local_and_aws_sanitized

attention:
  notify_on:
    - human_decision
    - unrecoverable_failure
    - repeated_supervisor_failure
  suppress_routine_success: true

approval:
  auto_allow:
    - test
    - lint
    - typecheck
    - local_build
  always_ask:
    - production_deploy
    - force_push
    - destructive_delete
    - secret_export

context:
  max_handoff_tokens: 12000
  auto_checkpoint_before_compaction: true

bench:
  immutable_raw_logs: true
```

---

# 55. PRODUCT NAMING

PEX is a working name and fits the pet concept.

Possible interpretations are unnecessary in the UI.

Do not waste development time forcing a tortured acronym.

If a stronger brand emerges, rename only if it improves presentation and does not disrupt delivery.

The mascot itself may be named Pex even if the product later receives a different formal name.

---

# 56. WHAT NOT TO BUILD

Do not let the product collapse into:

- another task board;
- another multi-agent chatroom;
- a wrapper where all work must originate inside PEX;
- a generic “AI manager” landing page with mocked agents;
- only a notification system;
- only a completion verifier;
- only shared memory;
- only a prompt enhancer;
- only a pet animation;
- only an MCP router;
- only a benchmark.

The value is in the **closed supervisory loop** across independent harnesses.

---

# 57. FIRST REAL END-TO-END TARGET

Before broadening integration count, get this exact story working deeply:

1. User opens existing Cursor session and existing Codex session.
2. PEX auto-discovers both.
3. User attaches persistent goals.
4. Both work.
5. Codex encounters a known context fact Cursor discovered.
6. PEX transfers only relevant context.
7. Cursor later attempts to stop before acceptance criteria.
8. PEX independently checks state and sends a corrective message.
9. Codex asks a routine permission.
10. PEX approves under policy.
11. A consequential choice appears.
12. PEX asks the human once, with recommendation/evidence.
13. User clicks decision on pet.
14. Work continues.
15. Both finish.
16. PEX shows verified completion evidence.
17. Full audit trail is available.

That single sequence demonstrates nearly the entire thesis.

---

# 58. BENCHMARK IMPLEMENTATION DETAILS

## 58.1 Run record

```json
{
  "run_id": "...",
  "task_id": "...",
  "harness": "cursor",
  "condition": "pex",
  "harness_version": "...",
  "model": "...",
  "model_settings": {},
  "pex_version": "...",
  "repo_commit": "...",
  "started_at": "...",
  "ended_at": "...",
  "success": true,
  "human_interventions": 1,
  "human_active_seconds": 23.4,
  "agent_input_tokens": 0,
  "agent_output_tokens": 0,
  "pex_input_tokens": 0,
  "pex_output_tokens": 0,
  "cost_usd": 0,
  "tool_calls": 0,
  "pex_interventions": [],
  "fail_reason": null,
  "raw_log_hash": "..."
}
```

## 58.2 Human intervention counter

A human intervention is any user action that alters or unblocks task execution:

- new corrective prompt;
- permission decision;
- manual context copy;
- restart/continue;
- choosing between alternatives;
- manual verification that leads to action.

Pure observation without action can be tracked separately.

When PEX acts autonomously, it is not counted as human intervention.

## 58.3 Active human time

Optional but powerful:

- timer starts when a decision/management UI receives focus;
- ends when user action completed;
- privacy-respecting;
- can be manually disabled.

## 58.4 Fairness

PEX must not have benchmark-only privileges unavailable in real product use.

---

# 59. BENCHMARK REPORT

Produce:

- `results.jsonl`
- `summary.csv`
- `analysis.ipynb` or script
- reproducible plots
- statistical report
- failed-run appendix
- exact harness/model versions
- benchmark task manifest
- PEX policy/config hash.

Never show only cherry-picked successful demos.

---

# 60. PRESENTATION CLAIMS — ALLOWED ONLY WITH EVIDENCE

Examples:

Allowed if measured:

> “PEX improved Cursor task success from X% to Y% on our frozen benchmark.”

> “Human interventions per successful Codex task fell by Z%.”

Not allowed without evidence:

> “PEX eliminates agent failures.”

> “PEX supports every coding agent perfectly.”

> “PEX saves 90% of developer time.”

---

# 61. THIRD-PARTY INTEGRATION LEGALITY

The hackathon rules require authorization to use third-party SDKs/APIs/data under their terms.

For each adapter:

- record official integration surface;
- license;
- whether redistribution is allowed;
- whether local hooks/plugins are user-installed;
- whether browser automation is permitted;
- whether credentials may be used programmatically.

Do not ship copied proprietary code.

---

# 62. SOURCE REFERENCES / CURRENT TECHNICAL EVIDENCE

These were current or recently crawled on August 25, 2026. Re-check before implementation.

## Hackathon
- Agents for Humans overview: `https://agentsforhumans.devpost.com/`
- Rules: `https://agentsforhumans.devpost.com/rules`
- FAQ: `https://agentsforhumans.devpost.com/details/faqs`

## Cursor
- Hooks: `https://cursor.com/docs/hooks` or current Cursor docs equivalent
- CLI: `https://cursor.com/docs/cli/overview`
- CLI/ACP: current Cursor CLI docs

## Codex
- OpenAI “Unlocking the Codex harness: how we built the App Server”:
  `https://openai.com/index/unlocking-the-codex-harness/`

## Claude Code
- Claude Agent SDK hooks:
  `https://code.claude.com/docs/en/agent-sdk/hooks`
- Agent SDK:
  `https://code.claude.com/docs/en/agent-sdk/overview`

## OpenCode
- Server API:
  `https://opencode.ai/docs/server/`
- CLI:
  `https://opencode.ai/docs/cli/`

## Devin
- API overview:
  `https://docs.devin.ai/api-reference/overview`
- v3 session APIs under official Devin docs.

## Grok Build
- Official docs:
  `https://docs.x.ai/build/overview`
- Open source:
  `https://github.com/xai-org/grok-build`

## Kimi Code
- Official docs:
  `https://www.kimi.com/code/docs/en/`
- Source:
  `https://github.com/MoonshotAI/kimi-code`

## Qwen Code
- Source:
  `https://github.com/QwenLM/qwen-code`
- Docs linked from repository.

## Hermes
- Docs:
  `https://hermes-agent.nousresearch.com/docs/`
- Source:
  `https://github.com/NousResearch/hermes-agent`

## OMP
- Source:
  `https://github.com/can1357/oh-my-pi`
- Project docs linked from repository.

## Prime Agent
- Source:
  `https://github.com/PrimeIntellect-ai/prime-agent`

For ambiguous/rapidly changing integrations such as Grok Bot, ZCode, DeepSeek harness variants, and any newly released products, find the current official interface before implementation.

---

# 63. FINAL CHECKLIST

## Product
- [ ] Pet works as always-on-top supervisor.
- [ ] User can attach persistent goal to existing session.
- [ ] Cursor deep integration works.
- [ ] Codex deep integration works.
- [ ] Cross-harness context transfer works.
- [ ] PEX can detect premature completion.
- [ ] PEX can verify at least several common claims externally.
- [ ] PEX can detect at least one trajectory drift/stagnation class early.
- [ ] PEX can handle routine approvals under policy.
- [ ] PEX escalates consequential decisions.
- [ ] PEX can apply and revert at least one JIT harness overlay.
- [ ] PEX can answer “what is happening?” without disturbing worker.
- [ ] Intervention audit trail works.
- [ ] Adapter health/capability matrix visible.
- [ ] Remote channel works if included in final demo.

## Engineering
- [ ] Strands Agents is central and non-trivial.
- [ ] AgentCore Runtime deployment works.
- [ ] Memory strategy implemented.
- [ ] Observability/traces work.
- [ ] Local policy cannot be bypassed by cloud.
- [ ] Secrets handled safely.
- [ ] Reconnect/restart works.
- [ ] Tests pass.
- [ ] Installer/setup documented.

## Harness targets
- [ ] Cursor
- [ ] Codex
- [ ] Claude Code
- [ ] Devin
- [ ] Grok Bot
- [ ] Grok Build
- [ ] Pi
- [ ] OpenCode
- [ ] Hermes
- [ ] OMP
- [ ] Prime Agent
- [ ] ZCode
- [ ] Kimi Code
- [ ] DeepSeek harness
- [ ] Qwen Code

The box means “strongest practical truthful adapter implemented,” not “pretend all capabilities are equal.”

## Benchmark
- [ ] Frozen task manifest.
- [ ] Cursor baseline.
- [ ] Cursor + PEX.
- [ ] Codex baseline.
- [ ] Codex + PEX.
- [ ] Same within-harness models/settings.
- [ ] Fresh environments.
- [ ] Objective hidden evaluation.
- [ ] Human intervention logging.
- [ ] PEX overhead included.
- [ ] Raw results immutable.
- [ ] Statistical analysis generated.
- [ ] Failure cases disclosed.

## Submission
- [ ] Public repo.
- [ ] MIT or Apache license.
- [ ] README.
- [ ] Architecture diagram.
- [ ] Max-5-minute public demo video.
- [ ] Devpost description.
- [ ] AWS Builder ID.
- [ ] Working/testable build.
- [ ] Optional live demo.
- [ ] Up to three qualifying builder.aws posts if eligible.

---

# 64. FINAL PRODUCT STANDARD

The final product should make this sentence true:

> I can open Cursor, Codex, Devin, Claude Code, OpenCode, Grok Build, or another supported agent as usual, tell PEX what I am actually trying to accomplish, and then mostly stop managing the mechanics of the agents.

PEX should know:

- what each worker is doing;
- why it is doing it;
- what it knows;
- what it forgot;
- whether it is actually progressing;
- whether its actions still serve the goal;
- whether another worker already solved part of its problem;
- whether its context/configuration should change;
- whether a safe approval can be handled;
- whether a claim is supported;
- whether the human actually needs to be interrupted.

The product is successful when the user is no longer the copy-paste bus, progress monitor, approval button, context cache, and “please continue” daemon for their AI tools.

**The user owns intent. PEX owns the babysitting.**
