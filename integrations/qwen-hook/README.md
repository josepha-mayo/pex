# Qwen Code to PEX

Qwen Code supports command hooks in TUI, headless, ACP, and `qwen serve` modes.
Merge `settings.fragment.json` into Qwen settings. The fragment passes
`--harness qwen` explicitly; replace the repository-relative command with the absolute path to
`integrations/hooks/pex_hook.py` unless Qwen always starts in this checkout.

Provision **Qwen** plus the exact project folder in **PEX Settings → Worker
integrations**, then set the one-time value as `PEX_HOOK_TOKEN` before launching
Qwen. Its first hook atomically binds the credential to that Qwen vendor
session. A hook from another session or project is rejected.

The command hook fails open if the loopback bridge is unavailable. Daemon control
is separate: PEX only advertises it after `/capabilities` negotiation and a
session-bound SSE stream have both succeeded.
The 7-second ordinary/permission and 42-second Stop client deadlines sit inside
Qwen's 10,000 ms and 45,000 ms command-hook deadlines.
