# Claude Code → PEX

PEX attaches to Claude Code through official Agent SDK hooks. It does not spawn Claude sessions.

Set `PEX_HARNESS=claude_code` (default in `integrations/hooks/pex_hook.py`) and merge `settings.fragment.json` into Claude Code settings.

Fail-open: if the bridge is down, the hook prints `{}` so Claude is not frozen.
