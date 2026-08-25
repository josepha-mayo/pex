# OpenCode / Qwen / Hermes / Kimi / OMP → PEX

Same fail-open stdin JSON hook as Claude Code. Set `PEX_HARNESS`:

| Harness | `PEX_HARNESS` | Official control (when live) |
| --- | --- | --- |
| Claude Code | `claude_code` | Agent SDK hooks |
| OpenCode | `opencode` | `opencode serve` HTTP |
| Qwen Code | `qwen` | `qwen serve` HTTP+SSE |
| Hermes | `hermes` | plugin hooks |
| Kimi Code | `kimi` | local server / ACP |
| OMP | `omp` | Node SDK / ACP |
| Pi | `pi` | extension events |
| Grok Build | `grok_build` | ACP / headless |
| Grok Bot | `grok_bot` | observe/notify only |
| Devin | `devin` | v3 session API |
| Prime | `prime` | experimental |
| ZCode | `zcode` | experimental |
| DeepSeek | `deepseek` | experimental |

```bash
PEX_HARNESS=hermes python integrations/hooks/pex_hook.py
```
