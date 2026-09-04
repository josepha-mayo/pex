# Claude Code → PEX

PEX attaches to Claude Code through official Agent SDK hooks. It does not spawn Claude sessions.

Merge `settings.fragment.json` into Claude Code settings. The fragment passes
`--harness claude_code` explicitly.

Replace the repository-relative script command in the fragment with the absolute
path to `integrations/hooks/pex_hook.py` unless Claude Code is always launched in
this checkout. PEX accepts only authenticated loopback hook requests.

Provision **Claude Code** plus the exact project folder in **PEX Settings →
Worker integrations**, then set the one-time value as `PEX_HOOK_TOKEN` before
launching Claude Code. Its first hook atomically binds the credential to that
Claude vendor session. A hook from another session or project is rejected.

Fail-open: if the bridge is down, the hook prints `{}` so Claude is not frozen.
The 7-second ordinary/permission and 42-second Stop client deadlines sit inside
the fragment's 10-second and 45-second hook deadlines.
