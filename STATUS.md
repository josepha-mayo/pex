# STATUS

**Current milestone:** Submission pack. Product loop is real locally. Devpost click, demo upload, and AgentCore still need the AWS/YouTube accounts on this machine.

**Date:** 2026-08-26

**Long-running goal:** Spec-complete PEX + real Devpost submit. Active until the entry is submitted.

## What works

- **Desktop-first attach:** this Cursor session via `~/.cursor/hooks.json`, Codex desktop (`ChatGPT.exe`) via App Server stdio, Grok Bot.exe observe-only. Do not spawn a second Cursor window. Do not confuse Grok Bot with Grok Build.
- **Pluggable supervisor LLM** (`pex_supervisor.providers`): OpenAI-compatible, Anthropic, Gemini, Bedrock, Ollama, LM Studio, llama.cpp, LiteLLM, custom base URL.
- **Web verification tools** with official endpoints: Firecrawl v2 search/scrape, Exa, Tavily, Brave, Serper, DuckDuckGo Instant Answer last resort.
- **Strands loop + high-stakes graph:** supervisor tools then independent verifier. `used_llm=true` only when a model actually ran. Tests set `PEX_SUPERVISOR_DISABLE=1`.
- Typed protocol, FastAPI bridge `127.0.0.1:7420`, SQLite, policy, cooldowns, secret redaction.
- Isolated Codex App Server path: `thread/start` only, fail-closed approvals, opaque bench workspaces.
- Four-arm driver: paired arms share one `TASK.md`. Treatment is `benchmarks/pex_attach.py` after the worker starts. Prompt stuffing is deleted and leakage-tested.
- Seven illustrated pets with mood sprites; ten generated Codex-v2 atlases; hatch-pet import. Open focuses the harness window; Pause stops supervision without poking the worker.
- AgentCore image + `/invocations` + `/ping` exist. AWS CLI and Docker are installed. Docker engine and AWS credentials were **not** available at last check, so Runtime is **not deployed**.

## What is invalid and must not be cited

The previous isolated Codex result (baseline 1/5, Codex+PEX 4/5) is **invalid experimental leakage**. Quarantined under `benchmarks/results/INVALID_LEAKED_RUNS_DO_NOT_USE/`. Do not put it on Devpost, in STATUS scores, or in the demo.

## Evidence

```bash
uv run pytest
uv run pytest tests/contract/test_live_supervisor.py   # skips without a supervisor key
uv run pytest tests/contract/test_live_opencode.py     # skips if serve is down
uv run pytest tests/contract/test_live_codex.py        # skips if Codex CLI is missing
```

Last local run: **92 passed, 2 skipped**.

## Remaining for the Devpost click

- AWS login + Docker engine, then AgentCore deploy to eu-north-1 (optional, strengthens Technical Implementation)
- ≤5-minute YouTube/Vimeo of live Cursor or Codex, using [`docs/SUBMISSION.md`](docs/SUBMISSION.md)
- 3 builder.aws.com posts from `docs/posts/`
- Frozen four-arm live jsonl (not required to submit; required before claiming lift)
