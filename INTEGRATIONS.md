# INTEGRATIONS

# Worker integrations

PEX negotiates support from evidence observed in the current connection. A registered
worker, installed binary, open port, initialize response, or injected test transport is
not by itself proof that PEX can observe or control that worker.

The verified release candidate at product source `af35707` includes the bridge and Cursor
helpers. Its extracted package inventories pass, but the installers are unsigned and a
fresh native smoke run remains outstanding after the reported machine freeze. The same source
passed a bounded live Codex App Server quiet contract and a same-thread recovery contract with
the saved free Muse/Strands supervisor: observed completion stayed NOOP; incomplete work earned
a specific nudge, produced the required artifact, recorded a helped outcome, and returned to
NOOP. This is source-bound semantic proof, not packaged native-app proof. See
[the submission evidence](docs/SUBMISSION.md), [sanitized live trace](docs/demo/evidence/LIVE_CODEX_STRANDS_2026-09-08.md),
and [package receipt](docs/PACKAGE_RECEIPT_AF35707.json).

Shared Codex is deliberately different from isolated Codex. The shared route can observe a
separately confirmed existing workspace through bounded, durable receipts, but sending,
steering, approvals, and configuration changes remain disabled. The isolated App Server
route may provide Deep support after attach and event-pump verification, but it starts or
attaches to an isolated Codex transport; it must never be presented as control of an
arbitrary ChatGPT/Codex desktop task. Workspace recovery details live in
[the local workspace-origin guide](docs/adapters/local-workspace-origin.md).

There is no single connect method. Cursor uses desktop hooks. Isolated Codex uses App
Server JSON-RPC. ChatGPT.exe is observe/focus only. OpenCode and Qwen use HTTP. Hermes,
Kimi, OMP, and Grok Build use ACP stdio. Devin uses the Organization API. Tailscale is
only a network overlay for loopback HTTP and is not a harness protocol.

Supervisor-model routing is a separate layer from worker harness integration. Settings
persists a versioned provider/model/auth/protocol/base URL snapshot plus an opaque native
keyring reference. Custom OpenAI-compatible and Anthropic-compatible endpoints are
locally constructor-tested; local Ollama/LM Studio/llama.cpp/vLLM modes and named API-key
providers retain their distinct auth contracts. Consumer login, AgentCore auth, Azure
OpenAI's deployment-specific contract, and generic SageMaker payload construction are
truthfully unavailable/degraded. No provider-live inference or packaged WinVault lifecycle
has been run for the current tree.

| Harness | Label | Connect | Official surface |
| --- | --- | --- | --- |
| Synthetic | Deep | in-process | Test/demo control surface. Not Cursor/Codex. |
| Cursor | Strong on hooks | `hooks` | **This Cursor.exe**. `~/.cursor/hooks.json` ([docs](https://cursor.com/docs/hooks.md)). `stop` → `followup_message`. `beforeShellExecution` → `permission` allow/deny/ask. Never a second Cursor window. Never leftover `cursor-agent` CLI. |
| Codex (isolated) | Deep after handshake | `app-server-stdio` | Isolated `codex app-server --listen stdio://` ([docs](https://developers.openai.com/codex/app-server)). `thread/list` → `data`. Explicit attach. Not ChatGPT.exe. |
| Codex (ChatGPT.exe) | Observe/focus | `observe-process` | **ChatGPT.exe**. Focus via the desktop process. Private JSON-RPC is unproven; do not treat presence as App Server Deep. |
| Grok Bot | Observe-only | `observe-process` | **Grok Bot.exe** ([docs](https://docs.x.ai/grok-bot/overview)). Cloud-computer teammates. **Not** Grok Build. No official local control API. |
| Grok Build | Basic after session/list; Strong with pump | `acp-stdio` | `grok agent stdio` ([docs](https://docs.x.ai/build/cli/headless-scripting)). Persisted sessions are loaded/resumed with absolute cwd before prompt. One-shot `grok -p` is not used by the adapter. Do not spawn unless asked. |
| OpenCode | Deep with HTTP | `http` | `opencode serve` ([docs](https://opencode.ai/docs/server/)). `GET /session`, `POST /session/:id/prompt_async`. A TUI process is not the API. |
| Qwen Code | Basic after capabilities; Strong with bound SSE or hooks | `http` + hooks | `qwen serve` (default :4170). PEX requires v1 features, an SSE stream bound to the exact session, and a `promptId` admission receipt. Permission votes remain session-bound in PEX and fail closed for unsupported designated/consensus identity policy. |
| Claude Code | Strong | `hooks` | Agent SDK / settings.json hook JSON. |
| Hermes | Basic with plugin; Strong with ACP pump | `acp-stdio` + plugin hooks | `hermes acp` ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)). `pre_tool_call` can block or escalate to Hermes' human gate; it cannot silently auto-approve. `on_session_end` observes but cannot resume. Do not launch desktop. |
| Kimi Code | Basic after session/list; Strong with pump | `acp-stdio` | `kimi acp`. STOP is the terminal `session/prompt` result and its `stopReason`, never a fabricated idle update. |
| OMP | Basic after session/list; Strong with pump | `acp-stdio` | `omp acp`. STOP is the terminal `session/prompt` result and its `stopReason`. Do not spawn unless asked. |
| Devin | Basic when API attached | `org-api` | `GET /v3/organizations/{org_id}/sessions/{id}` until `exit`/`error`/`suspended`; nudge via `POST .../messages` ([docs](https://docs.devin.ai/api-reference/overview)). Do not launch Devin.exe. |
| Pi | Unavailable | unresolved | Registry target only; no provider-specific hook/control integration is implemented. |
| Prime / ZCode / DeepSeek | Unavailable | unresolved | Identify the exact product and implement its authenticated surface before claiming support. |

**Tailscale:** not installed here. If present later, use `tailscale serve` only in front of HTTP loopback (PEX bridge, `opencode serve`, `qwen serve`). It does not replace hooks, App Server, or ACP.

Hook ingest is explicit: Cursor has `/v1/hooks/cursor`; Claude Code and Qwen use
their documented command-hook schemas; Hermes uses its plugin. The generic command
helper rejects every other harness, so an arbitrary POST cannot manufacture liveness.

Authenticated release setup starts in **PEX Settings → Worker integrations**.
The operator pre-registers an exact harness and project, copies only the returned
scoped environment credential into the worker launch environment, and the first
valid hook atomically binds it to that vendor session. Cross-harness,
cross-session, cross-project, expired, rotated, and revoked credentials fail
closed; the worker never receives the desktop operator bearer.

Loopback: `GET /v1/discover` lists running desktops first, then HTTP daemons, then CLIs. Each item includes `connect`. `POST /v1/discover/attach` uses that method. Cursor attach installs hooks only.
