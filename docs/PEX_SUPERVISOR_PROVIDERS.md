# Supervisor model providers (BYOK, login, local, custom)

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
