# PEX — CORE BUILD SPEC
## Read this before touching the code

**Hackathon:** AWS + Devpost Agents for Humans Hackathon  
**Target track:** Professional Agents

---

# 0. THE ONE-SENTENCE PRODUCT

PEX is an **independent, goal-aware supervisor that sits above existing coding-agent harnesses, watches what they actually do, and autonomously handles the repetitive human work of supervising them.**

The human gives goals and makes real decisions.

**PEX handles the babysitting.**

---

# 1. DO NOT MISUNDERSTAND THIS PRODUCT

PEX is **NOT**:

- a better prompt;
- a prompt suffix;
- a benchmark wrapper;
- a static system prompt;
- a task-specific rules engine;
- a verifier that only checks at the end;
- a dashboard;
- another coding harness;
- a multi-agent chatroom;
- a notification app;
- a hardcoded `if X then tell agent Y` script.

If the implementation can be summarized as:

> **“Codex gets extra instructions when PEX is enabled.”**

then the implementation is wrong.

PEX must be a **separate running agent/system** that observes a worker after it has begun working and decides, from legitimate evidence, whether intervention is needed.

---

# 2. WHAT PEX ACTUALLY DOES

A user may have Cursor, Codex, Claude Code, Devin, OpenCode, Grok Build, Pi, Hermes, OMP, Kimi Code, Qwen Code, and other agents running independently.

PEX attaches above them.

For each active worker, PEX should know:

- the actual persistent goal;
- acceptance criteria;
- important constraints and prior decisions;
- what the worker currently knows;
- what files/processes/tests changed;
- whether real progress is happening;
- whether the worker is drifting;
- whether context is degrading;
- whether another agent already discovered useful information;
- whether the worker stopped too early;
- whether its claims are supported by external state;
- whether a permission can safely be handled automatically;
- whether the human genuinely needs to be interrupted.

Then PEX acts.

### Premature stop
Codex stops. PEX checks actual observable state. Tests still fail. PEX sends the failure evidence back and tells Codex to continue.

PEX **discovers** the problem from state. It is not told the benchmark answer.

### Context handoff
Cursor discovers an important fact. Later Codex needs it. PEX notices relevance, extracts the minimum useful context, and sends it to Codex.

The user does not manually copy/paste anything.

### Drift
An agent spends dozens of actions on a side issue that no longer serves the persistent goal. PEX notices that the trajectory is no longer producing useful progress and redirects it.

### Wrong dependency order
An agent begins an expensive downstream step before a required artifact exists. PEX detects the missing prerequisite and redirects it before time is wasted.

### Permission
An agent asks whether it may run tests. PEX checks local policy. Safe routine action: approve. Production migration or destructive action: ask the human.

### False completion
The worker says the evaluation is complete. PEX checks the output and finds only 27/30 rows. PEX rejects the claim and returns the evidence to the worker.

### User mistake
The user sends a prompt contradicting an active persistent constraint. PEX catches it before delivery and asks whether the user is intentionally overriding the earlier decision.

---

# 3. THE CLOSED LOOP

This loop is the product:

```text
USER GOAL
   ↓
PERSISTENT INTENT + ACCEPTANCE CRITERIA
   ↓
EXISTING WORKER AGENT
   ↓
REAL HARNESS EVENTS + FILES + TESTS + PROCESS STATE
   ↓
PEX OBSERVES
   ↓
PEX REASONS
   ↓
PEX DECIDES
   - do nothing
   - nudge
   - inject context
   - continue session
   - approve/deny routine permission
   - reconfigure harness
   - fresh handoff
   - verify claim
   - ask human
   ↓
ACTION EXECUTED THROUGH REAL HARNESS ADAPTER
   ↓
PEX OBSERVES RESULT
   ↓
LOOP CONTINUES
```

If this loop is not real, PEX is not implemented.

---

# 4. PEX MUST BE AN ACTUAL AGENT

Use **Strands Agents SDK** meaningfully.

Preferred architecture:

```text
Cursor / Codex / Claude / OpenCode / ...
                 ↓
        local adapter layer
                 ↓
         normalized events
                 ↓
        PEX Strands supervisor
                 ↓
        structured intervention
                 ↓
          local policy guard
                 ↓
        real harness action
```

Use Amazon Bedrock / AgentCore for the supervisor where appropriate for the hackathon.

There must be real model inference.

Logs must prove:

- what PEX observed;
- which model/backend was called;
- what PEX concluded;
- what action it selected;
- what action was actually sent;
- what happened afterward.

Deterministic code should handle deterministic facts. Semantic supervision should use the real supervisor.

Do **not** fake an “agent” with benchmark conditionals or treatment-only strings.

---


---

# 4.1 SUPERVISOR MODEL PROVIDERS (BYOK, LOGIN, LOCAL, CUSTOM)


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

---

# 5. PERSISTENT INTENT IS CENTRAL

PEX does not treat the latest chat message as the whole objective.

Each job has a durable goal record containing:

```text
objective
acceptance criteria
constraints
non-goals
important decisions
rejected approaches
required evidence
```

PEX continuously compares worker behavior against this record.

The user may explicitly update or override it. PEX must not cling to stale intent after an intentional change.

---

# 6. CONTEXT BELONGS TO THE PROJECT, NOT THE CHAT

PEX maintains project-level context.

Useful information can move between workers.

PEX may collect:

- decisions;
- facts;
- test results;
- discovered root causes;
- file paths;
- experiment outcomes;
- unresolved blockers;
- completed investigations;
- important rejected approaches.

PEX must not dump full transcripts by default. It should send the **smallest sufficient context bundle**.

Every handoff fact must come from information PEX legitimately observed.

Never manufacture context from benchmark metadata.

---

# 7. JIT HARNESS ADAPTATION

PEX may temporarily reshape a worker environment for the current phase.

Examples:

### Research
- enable web/search;
- read-only repo where appropriate;
- stronger evidence requirements.

### Implementation
- code/test/LSP tools;
- reduce irrelevant research tools;
- inject acceptance criteria.

### Debugging
- pin reproduction command;
- emphasize logs/debugger;
- preserve failing state.

### Evaluation
- immutable benchmark config;
- deterministic scripts;
- completion gated on expected artifacts.

Possible overlays:

- project/system instructions;
- tools;
- MCP servers;
- model;
- reasoning effort;
- context bundle;
- permission rules;
- token budget;
- verifier;
- sandbox/worktree policy.

Changes should be reversible.

---

# 8. THE DESKTOP PET

PEX should feel like a small autonomous companion, not enterprise-dashboard sludge.

Compact states:

> `4 working · 0 need you`

> `Codex drifting → corrected`

> `Context shared → Cursor`

> `Devin needs a decision`

Clicking expands:

- current goal;
- latest meaningful progress;
- what PEX did;
- why;
- evidence;
- open agent;
- ask PEX;
- pause supervision;
- undo reversible action.

The user should be able to ask:

> what is Codex doing?

> why did you interrupt Cursor?

> what needs me right now?

without interrupting the worker itself.

---

# 9. HARNESS SUPPORT

Target integrations:

- Cursor
- Codex
- Claude Code
- Devin
- Grok Bot
- Grok Build
- Pi
- OpenCode
- Hermes
- OMP / Oh My Pi
- Prime Agent
- ZCode
- Kimi Code
- DeepSeek harness
- Qwen Code

Use the strongest truthful interface available:

1. official API/server/SDK;
2. ACP or equivalent;
3. hooks/plugins/extensions;
4. structured headless mode;
5. stable local session data;
6. PTY/process integration;
7. accessibility/browser automation only as fallback.

Every adapter reports its real capabilities. Do not pretend every harness supports identical control.

**Cursor and Codex are the first deep targets and benchmark targets.**

Do not sacrifice deep working supervision merely to claim 15 shallow integrations.

---

# 10. THE BENCHMARK: ABSOLUTE RULES

The previous `4/5 vs 1/5` result is **INVALID**.

Do not reuse it anywhere.

Four arms:

1. Cursor baseline
2. Cursor + PEX
3. Codex baseline
4. Codex + PEX

Primary comparison is within harness.

---

# 11. BASELINE AND TREATMENT MUST START EQUIVALENT

For a given task:

```text
Codex baseline receives:
TASK.md

Codex + PEX receives:
TASK.md
```

Not:

```text
Codex baseline:
TASK.md

Codex + PEX:
TASK.md
+ "do not stop until tests pass"
+ "do not claim done"
+ secret handoff fact
+ better task-specific instructions
```

That is **prompt leakage**, not PEX.

The treatment worker must not receive extra task-solving information merely because PEX is enabled.

The difference is that an independent PEX supervisor is attached during the treatment run.

---

# 12. PEX GETS CAPABILITIES, NEVER ANSWERS

PEX may access:

- persistent user goal;
- public task description;
- worker events;
- worker transcript;
- repository files normally available;
- file changes;
- commands/tool output;
- visible tests;
- process state;
- other legitimately supervised sessions;
- context discovered during real work;
- configured user policies.

PEX may **NOT** access:

- hidden evaluator;
- expected solution;
- planted bug explanation;
- stressor label;
- expected supervisor action;
- benchmark oracle;
- treatment-only acceptance criteria;
- task-specific intervention string;
- privileged handoff fact;
- anything derived from hidden ground truth.

---

# 13. PRIVATE BENCHMARK BOUNDARY

Architecture must enforce:

```text
PRIVATE BENCHMARK CONTROLLER
    stressor metadata
    hidden evaluator
    expected behavior
           │
           │ ZERO ACCESS
           X
           │
     ┌─────┴─────┐
     │           │
  WORKER        PEX
```

The benchmark controller may score the run.

It may **never teach PEX how to win the run**.

Automated tests must enforce this boundary.

---

# 14. NO HARDCODED PEX BEHAVIOR

Forbidden:

```python
if task_id == "handoff_03":
    send("schema.json is the source of truth")
```

Forbidden:

```python
if stressor == "premature_stop":
    send("run pytest and continue")
```

Forbidden:

```python
if condition == "pex":
    append_better_prompt()
```

Correct:

```text
worker stops
→ PEX observes stop
→ PEX checks persistent acceptance criteria
→ PEX checks actual workspace/test state
→ PEX concludes work is incomplete
→ PEX independently formulates correction
→ PEX sends correction
```

Correct:

```text
Cursor discovers schema fact
→ PEX records it with provenance
→ Codex later works on related code
→ PEX detects relevance
→ PEX transfers the fact
```

---

# 15. BENCHMARK METRICS

Primary:

> **Task success rate**

Headline secondary:

> **Human interventions per successful task**

Also record:

- wall time;
- human active management time;
- worker tokens;
- PEX tokens;
- combined cost;
- PEX inference count;
- PEX interventions;
- useful interventions;
- harmful interventions;
- false-done count;
- premature-stop count;
- repeated tool calls;
- approvals handled;
- context handoffs;
- context resets;
- successful task per dollar.

PEX overhead counts. Never hide it.

---

# 16. BENCHMARK INTEGRITY TESTS

Before any benchmark run, automated tests must prove:

- baseline and treatment public task prompts hash identically;
- baseline and treatment start from equivalent repo state;
- PEX cannot read hidden evaluator;
- PEX cannot read stressor metadata;
- PEX cannot read expected behavior;
- no treatment-only prompt suffix exists;
- no oracle handoff fact exists;
- final evaluator is isolated;
- task IDs cannot trigger task-specific supervisor logic;
- PEX interventions are traceable to legitimate observed evidence;
- raw logs are immutable.

If any test fails, benchmark execution must abort.

---

# 17. EVERY PEX INTERVENTION MUST BE AUDITABLE

Store:

```text
timestamp
session
persistent goal
observable evidence
PEX backend/model
inference request ID
diagnosis
proposed action
policy result
actual action sent
result afterward
```

For every benchmark win, we must be able to answer:

> What did PEX know?

> How did PEX know it?

> Why did PEX intervene?

If we cannot answer those, the result is untrustworthy.

---

# 18. REAL PRODUCT TESTS

Required scenarios:

1. worker stops with incomplete acceptance criteria;
2. worker says tests pass when tests were never run;
3. benchmark output has missing rows;
4. repeated identical error loop;
5. downstream work starts before prerequisite exists;
6. worker drifts into unrelated refactor;
7. context is lost/compacted;
8. another agent has useful context;
9. routine approval request;
10. dangerous approval request;
11. contradictory user prompt;
12. abandoned background process;
13. duplicate work across agents;
14. cloud supervisor unavailable;
15. malformed adapter event;
16. harmful PEX intervention must be reversible.

---

# 19. DEVELOPMENT ORDER

Do not jump to benchmark scores before the actual product exists.

## Phase 1: real PEX supervisor
- Strands;
- real model inference;
- local bridge;
- event normalization;
- persistent intent;
- intervention log.

## Phase 2: deep Codex adapter
PEX must observe real events, send real messages, handle real approvals, detect stopping, and inspect external state.

## Phase 3: deep Cursor adapter
Same bar.

## Phase 4: supervisor behaviors
- premature stop;
- false completion;
- drift/stagnation;
- dependency guard;
- context handoff;
- approval broker;
- user-prompt conflict.

## Phase 5: pet UI

## Phase 6: JIT harness adaptation

## Phase 7: additional harnesses

## Phase 8: only now run the real four-arm benchmark

---

# 20. DEFINITION OF A REAL DEMO

A valid demo should show:

1. User starts Codex and Cursor normally.
2. PEX discovers both.
3. User gives each persistent goal.
4. Both agents work.
5. Cursor discovers information useful to Codex.
6. PEX transfers it without human copy/paste.
7. Codex stops too early.
8. PEX checks actual state and resumes it.
9. Cursor asks for safe test permission.
10. PEX approves under policy.
11. A consequential choice appears.
12. PEX asks the human once with evidence/recommendation.
13. Work completes.
14. PEX verifies completion.
15. Audit trail shows exactly what PEX did and why.

No scripted fake messages.

No benchmark oracle.

No hidden prompt suffix.

---

# 21. HACKATHON FIT

Hackathon:
`https://agentsforhumans.devpost.com/`

Target: **Professional Agents**.

PEX fits because managing autonomous AI workers has itself become repetitive, judgment-heavy professional work.

The submission should prove:

### Technical Implementation
Real cross-harness supervision, Strands, AgentCore where useful, adapters, event loop, policy, context, real interventions.

### Design
A quiet, useful pet experience that keeps the human out of unnecessary management.

### Impact
Measured task-success lift and reduced human intervention.

### Originality
Not another orchestrator. PEX continuously adapts independent existing harnesses around persistent human intent.

### Presentation
Show the real closed loop live.

---

# 22. THE CORE PRODUCT CLAIM

Do not claim:

> “PEX gives agents better prompts.”

Do not claim:

> “PEX is a multi-agent dashboard.”

Do not claim:

> “PEX verifies agent output.”

The actual claim is:

> **PEX removes the new human-management workload created by autonomous AI agents.**

The user should not need to be:

- the copy-paste bus;
- the context cache;
- the progress monitor;
- the approval button;
- the “please continue” daemon;
- the false-done detector;
- the session coordinator;
- the token-waste investigator.

**The user owns intent. PEX owns the babysitting.**

---

# 23. FINAL RULE FOR THE IMPLEMENTATION AGENT

You are free to improve architecture, tools, UI, models, adapters, algorithms, tests, and scope.

You are **not** free to redefine PEX into an easier product.

When something is difficult:

> **solve the difficult thing.**

Do not replace autonomous supervision with privileged prompting.

Do not fake a benchmark.

Do not optimize the benchmark instead of the product.

Do not report success merely because a number looks good.

A valid `4/10` is worth more than a contaminated `10/10`.

**Build the actual supervisor.**
