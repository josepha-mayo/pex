# INTEGRATIONS

Live capability matrix. Labels are truthful. Deep means a live or injected official control transport is attached. Registration alone is never Deep.

There is **no single connect method**. Cursor is this desktop via hooks. Codex is App Server JSON-RPC. Grok Bot is observe-only. Grok Build is `grok agent stdio`. OpenCode/Qwen are HTTP. Hermes/Kimi/OMP are ACP stdio. Devin is the Organization API. Tailscale is a network overlay for HTTP loopback, not a harness protocol, and is **not installed** on this machine.

| Harness | Label | Connect | Official surface |
| --- | --- | --- | --- |
| Synthetic | Deep | in-process | Test/demo control surface. Not Cursor/Codex. |
| Cursor | Strong on hooks | `hooks` | **This Cursor.exe**. `~/.cursor/hooks.json` ([docs](https://cursor.com/docs/hooks.md)). `stop` → `followup_message`. `beforeShellExecution` → `permission` allow/deny/ask. Never a second Cursor window. Never leftover `cursor-agent` CLI. |
| Codex | Deep after handshake | `app-server-stdio` | **ChatGPT.exe**. `codex app-server --listen stdio://` ([docs](https://developers.openai.com/codex/app-server)). `thread/list` → `data`. Same `~/.codex` as the desktop. |
| Grok Bot | Observe-only | `observe-process` | **Grok Bot.exe** ([docs](https://docs.x.ai/grok-bot/overview)). Cloud-computer teammates. **Not** Grok Build. No official local control API. |
| Grok Build | Strong until ACP handshake | `acp-stdio` | `grok agent stdio` ([docs](https://docs.x.ai/build/cli/headless-scripting)). One-shot: `grok -p`. `~/.grok/bin/grok.exe`. Do not spawn unless asked. |
| OpenCode | Deep with HTTP | `http` | `opencode serve` ([docs](https://opencode.ai/docs/server/)). `GET /session`, `POST /session/:id/prompt_async`. A TUI process is not the API. |
| Qwen Code | Deep with HTTP | `http` | `qwen serve` (default :4170). |
| Claude Code | Strong | `hooks` | Agent SDK / settings.json hook JSON. |
| Hermes | Strong → Deep with ACP | `acp-stdio` | `hermes acp` ([docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/acp)). Do not launch the desktop. |
| Kimi Code | Strong → Deep with ACP | `acp-stdio` | `kimi acp`. |
| OMP | Strong → Deep with ACP | `acp-stdio` | `omp acp`. |
| Devin | Basic when API attached | `org-api` | `https://api.devin.ai/v3/organizations/{org_id}/sessions` ([docs](https://docs.devin.ai/api-reference/overview)). Do not launch Devin.exe. |
| Pi | Basic | `extension-events` | No native permission popups. |
| Prime / ZCode / DeepSeek | Experimental | unknown | Identify the exact product before claiming a transport. |

**Tailscale:** not installed here. If present later, use `tailscale serve` only in front of HTTP loopback (PEX bridge, `opencode serve`, `qwen serve`). It does not replace hooks, App Server, or ACP.

Hook ingest: `POST /v1/hooks/{harness}` plus Cursor mapping on `/v1/hooks/cursor`. Generic client: `integrations/hooks/pex_hook.py`.

Loopback: `GET /v1/discover` lists running desktops first, then HTTP daemons, then CLIs. Each item includes `connect`. `POST /v1/discover/attach` uses that method. Cursor attach installs hooks only.
