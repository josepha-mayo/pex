# Claude Code and Qwen Code command hooks

`pex_hook.py` is only for the official Claude Code and Qwen Code command-hook
contracts. It intentionally rejects every other `PEX_HARNESS` value. OpenCode,
Hermes, Kimi, OMP, Grok Build, and Devin use their adapter-specific HTTP, plugin,
ACP, or API surfaces; posting a generic heartbeat must never make them look live.

Install the matching fragment. Each command passes an explicit `--harness`
value, so Claude and Qwen can coexist without a process-global `PEX_HARNESS`.
Replace the repository-relative command with the absolute path to `pex_hook.py`
unless the harness always starts in the PEX checkout.

Before starting a new hooked session, open **PEX Settings → Worker
integrations**, select the harness and exact project folder, and create the
one-time scoped credential. Set the displayed value as `PEX_HOOK_TOKEN` in the
environment that launches Claude Code or Qwen Code. The first valid hook binds
that credential to its vendor session; another session or project cannot reuse
it. Rotating or revoking it never exposes the bridge operator bearer.

The hook only sends to an HTTP loopback bridge, limits request/response sizes,
prints only fields supported by the hook protocol, and fails open with `{}` if
the local bridge is unavailable. Client deadlines are 7 seconds for ordinary
and permission hooks and 42 seconds for Stop; the fragments leave a 3-second
outer margin (10 and 45 seconds respectively).
